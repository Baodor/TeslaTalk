"""Explicitly reviewed itinerary imports and consented next-stop navigation.

Tesla's current official command proxy only supports navigation_request among
the navigation commands. We send one shared stop at a time and never claim
that GPS coordinates or an HTTP acknowledgement prove charger recognition.
"""
import hashlib
import json
import re
import time
import uuid
from typing import Literal
from urllib.parse import urlencode
from xml.etree import ElementTree
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import db, fleet


class Stop(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=200)
    latitude: float = Field(ge=-90,le=90,allow_inf_nan=False)
    longitude: float = Field(ge=-180,le=180,allow_inf_nan=False)
    kind: str = Field(default='waypoint',pattern='^(waypoint|charging|destination)$')
    operator: str = Field(default='',max_length=100)
    address: str = Field(default='',max_length=300)
    google_place_id: str | None = Field(default=None,max_length=256,pattern='^[A-Za-z0-9_-]+$')
    charger_id: int | None = Field(default=None,gt=0)
    network_id: int | None = Field(default=None,gt=0)
    arrival_soc: float | None = Field(default=None,ge=0,le=100,allow_inf_nan=False)
    departure_soc: float | None = Field(default=None,ge=0,le=100,allow_inf_nan=False)
    charge_minutes: float | None = Field(default=None,ge=0,le=100000,allow_inf_nan=False)

    @field_validator('name')
    @classmethod
    def nonempty(cls,value):
        value=value.strip()
        if not value:raise ValueError('Ein Stopp benötigt einen Namen.')
        return value


class Plan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title: str = Field(min_length=1,max_length=200)
    stops: list[Stop] = Field(min_length=1,max_length=50)
    source: Literal['import','abrp'] = 'import'
    origin: Stop | None = None
    route_points: list[tuple[float,float]] = Field(default_factory=list,max_length=20000)
    distance_km: float | None = Field(default=None,ge=0,le=100000,allow_inf_nan=False)
    duration_minutes: float | None = Field(default=None,ge=0,le=100000,allow_inf_nan=False)
    @field_validator('route_points')
    @classmethod
    def valid_route(cls,points):
        import math
        if any(not math.isfinite(lat+lon) or not -90<=lat<=90 or not -180<=lon<=180 for lat,lon in points):raise ValueError('Ungültige Routenlinie.')
        return points
    @field_validator('title')
    @classmethod
    def title_not_blank(cls,value):
        value=value.strip()
        if not value:raise ValueError('Ein Ladeplan benötigt einen Namen.')
        return value


class Upload(BaseModel):
    filename: str = Field(min_length=1,max_length=200)
    content: str = Field(min_length=1,max_length=700_000)
    encoding: Literal['text','base64'] = 'text'


class SendStop(BaseModel):
    request_id: uuid.UUID
    version: str = Field(min_length=1,max_length=80)
    stop_index: int = Field(ge=0,le=49)


class ChargerConfirmation(BaseModel):
    version: str = Field(min_length=1,max_length=80)
    stop_index: int = Field(ge=0,le=49)
    recognized: bool
    preconditioning: bool = False


def local(tag):return tag.rsplit('}',1)[-1].lower()


def parse_upload(upload):
    """Only supplied local text is parsed; no fetching of links or XML entities."""
    extension=upload.filename.lower().rsplit('.',1)[-1]
    try:
        if extension in ('xlsx','csv'):
            from .route_uploads import table_plan
            return Plan.model_validate(table_plan(upload)).model_dump()
        if upload.encoding!='text' or len(upload.content.encode())>500_000:raise ValueError()
        if extension=='json':
            document=json.loads(upload.content)
            if not isinstance(document,dict):raise ValueError()
            # Our lossless interchange format; raw ABRP responses are not guessed.
            return Plan.model_validate({key:document[key] for key in ('title','stops','source','origin','route_points','distance_km','duration_minutes') if key in document}).model_dump()
        if extension!='gpx':
            raise HTTPException(422,'Bitte eine GPX-, Excel-, CSV-Datei oder einen TeslaTalk-JSON-Export hochladen.')
        if re.search(r'<!\s*(DOCTYPE|ENTITY)',upload.content,re.I):raise ValueError()
        root=ElementTree.fromstring(upload.content)
        if local(root.tag)!='gpx':raise ValueError()
        routes=[node for node in root if local(node.tag)=='rte']
        if len(routes)>1:raise HTTPException(422,'Bitte genau eine Route mit ihren Stopps exportieren.')
        waypoints=[node for node in root if local(node.tag)=='wpt']
        points=[node for node in routes[0] if local(node.tag)=='rtept'] if routes else waypoints
        # Dense track points are geometry, never inferred charging stops.
        if not points or len(points)>50:
            raise HTTPException(422,'Der Export enthält keine Stopp-Liste oder mehr als 50 Stopps. Reine GPS-Tracks sind keine Ladepläne.')
        stops=[]
        for index,point in enumerate(points):
            fields={local(node.tag):(node.text or '').strip() for node in point.iter()}
            name=next(((node.text or '').strip() for node in point if local(node.tag)=='name'),None)
            if not name:raise HTTPException(422,'Im GPX fehlen benannte Stopps. Bitte den Plan mit Ladehalten exportieren.')
            description=' '.join(fields.get(key,'') for key in ('type','sym','name','desc'))
            charging=bool(re.search(r'\b(supercharger|charging(?:station)?|charger|ionity|fastned|enbw|allego|aral\s+pulse|ladestation|ladehalt|ladesäule|ladepunkt)\b',description,re.I))
            stops.append(Stop(name=name,latitude=float(point.attrib['lat']),longitude=float(point.attrib['lon']),
                              kind='charging' if charging else 'destination' if index==len(points)-1 else 'waypoint',
                              operator=fields.get('operator','')[:100],address=fields.get('address','')[:300],
                              google_place_id=fields.get('google_place_id') or fields.get('googleplaceid') or None).model_dump())
        title=next(((node.text or '').strip() for node in routes[0] if local(node.tag)=='name'), '') if routes else ''
        return Plan(title=title or upload.filename[:200],stops=stops).model_dump()
    except HTTPException:raise
    except (ValueError,TypeError,KeyError,ElementTree.ParseError,RecursionError):
        raise HTTPException(422,'Die Routen-Datei ist ungültig oder enthält kein unterstütztes Stopp-Format.') from None


def snapshot(trip_id):
    row=db.one('SELECT * FROM charging_plans WHERE trip_id=?',(trip_id,))
    if not row:return None
    return json.loads(row['data'])|{'version':row['version'],'current_stop':row['current_stop'],
        'transfer_mode':'next_stop','confirmations':db.all_rows("SELECT c.user_id,c.version,c.stop_index,c.recognized,c.preconditioning,c.updated_at FROM charging_confirmations c JOIN members m ON m.trip_id=c.trip_id AND m.user_id=c.user_id AND m.vehicle_id=c.vehicle_id WHERE c.trip_id=? AND m.left_at IS NULL AND m.role='driver'",(trip_id,))}


def save(trip_id,plan):
    version=str(uuid.uuid4())
    with db.connect() as connection:
        old=connection.execute('SELECT current_stop FROM charging_plans WHERE trip_id=?',(trip_id,)).fetchone()
        if old and old['current_stop'] is not None:
            connection.execute('DELETE FROM trip_planners WHERE trip_id=?',(trip_id,))
            connection.execute('DELETE FROM trip_navigation WHERE trip_id=?',(trip_id,))
        connection.execute('INSERT INTO charging_plans VALUES (?,?,?,NULL,?) ON CONFLICT(trip_id) DO UPDATE SET version=excluded.version,data=excluded.data,current_stop=NULL,created_at=excluded.created_at',
                           (trip_id,version,json.dumps(plan.model_dump(),ensure_ascii=False),time.time()))
        connection.execute('DELETE FROM charging_confirmations WHERE trip_id=?',(trip_id,))
    return snapshot(trip_id)


def navigation_text(stop):
    # A specific Google Places charger reference is preserved when supplied.
    # A text/coordinate search is a fallback, not a confirmed Tesla charger POI.
    params={'api':'1','query':f"{stop['name']} {stop['latitude']:.7f},{stop['longitude']:.7f}"}
    if stop.get('google_place_id'):params['query_place_id']=stop['google_place_id']
    url='https://www.google.com/maps/search/?'+urlencode(params)
    return stop['name']+'\n'+stop.get('address','')+'\n'+url


def active_plan(trip_id):
    row=db.one('SELECT * FROM charging_plans WHERE trip_id=? AND current_stop IS NOT NULL',(trip_id,))
    if not row:return None
    document=json.loads(row['data'])
    return row,document['stops'][row['current_stop']]


async def distribute_current(trip, planning=None, guard=None):
    if planning is None:
        from . import route_planning as planning
    current=active_plan(trip['id'])
    if not current:return []
    row,stop=current
    key=hashlib.sha256((row['version']+':'+str(row['current_stop'])).encode()).hexdigest()
    results=[]
    for following in db.all_rows('SELECT * FROM route_followers WHERE trip_id=?',(trip['id'],)):
        if guard:guard()
        try:vehicle=planning.car(trip['id'],following['user_id'])
        except HTTPException:continue
        if vehicle['id']!=following['vehicle_id']:continue
        status='accepted' if following['command_key']==key and following['status'] in ('unconfirmed','matching','source_ready') else 'unknown' if following['status']=='sending' else 'error'
        message='Navi-Befehl angenommen; Ladestation und Vorkonditionierung im Auto prüfen.'
        if following['command_key']!=key:
            planning.active(trip['id'])
            db.execute("UPDATE route_followers SET command_key=?,sent_at=?,status='sending',problem=NULL WHERE trip_id=? AND user_id=?",(key,time.time(),trip['id'],following['user_id']))
            try:
                if guard:await fleet.send_navigation(following['user_id'],vehicle,navigation_text(stop),trip['id'],guard=guard)
                else:await fleet.send_navigation(following['user_id'],vehicle,navigation_text(stop),trip['id'])
                planning.active(trip['id'])
                status='accepted'
                db.execute("UPDATE route_followers SET status='unconfirmed' WHERE trip_id=? AND user_id=?",(trip['id'],following['user_id']))
            except (HTTPException,httpx.HTTPError) as error:
                status='unknown' if isinstance(error,httpx.HTTPError) or error.status_code>=500 else 'error'
                message=error.detail if isinstance(error,HTTPException) else 'Tesla hat den Befehl nicht bestätigt; Ergebnis bitte am Auto prüfen.'
                db.execute("UPDATE route_followers SET status='error',problem='command_error' WHERE trip_id=? AND user_id=?",(trip['id'],following['user_id']))
        if status=='error':message='Ergebnis der bisherigen Übertragung prüfen; zum Wiederholen eigene Routenfreigabe erneut bestätigen.'
        results.append({'user_id':following['user_id'],'vehicle_id':vehicle['id'],'status':status,'message':message})
    return results


async def send(trip,body,planning,guard=None):
    async with planning.lock(trip['id']):
        planning.active(trip['id'])
        if guard:guard()
        payload=json.dumps({'version':body.version,'stop_index':body.stop_index},sort_keys=True)
        previous=db.one('SELECT * FROM charging_batches WHERE trip_id=? AND request_id=?',(trip['id'],str(body.request_id)))
        if previous:
            if previous['payload']!=payload:raise HTTPException(409,'Diese Auftrags-ID gehört zu einem anderen Routenstopp.')
            return json.loads(previous['result'])
        row=db.one('SELECT * FROM charging_plans WHERE trip_id=?',(trip['id'],))
        if not row or row['version']!=body.version:raise HTTPException(409,'Der Ladeplan wurde geändert. Bitte die Übersicht aktualisieren.')
        if body.stop_index>=len(json.loads(row['data'])['stops']):raise HTTPException(422,'Dieser Routenstopp existiert nicht.')
        vehicle=planning.car(trip['id'],trip['leader_id'])
        # The leader's own car is explicitly enrolled by this send action.
        db.execute("INSERT INTO route_followers(trip_id,user_id,vehicle_id,accepted_at) VALUES (?,?,?,?) ON CONFLICT(trip_id,user_id) DO UPDATE SET vehicle_id=excluded.vehicle_id,accepted_at=excluded.accepted_at",(trip['id'],trip['leader_id'],vehicle['id'],time.time()))
        if not planning.planner_id(trip):
            db.execute('INSERT INTO trip_planners VALUES (?,?,?)',(trip['id'],trip['leader_id'],vehicle['id']))
        db.execute('UPDATE charging_plans SET current_stop=? WHERE trip_id=?',(body.stop_index,trip['id']))
        if row['current_stop']!=body.stop_index:
            db.execute('DELETE FROM trip_navigation WHERE trip_id=?',(trip['id'],))
        pending={'request_id':str(body.request_id),'status':'unknown','vehicles':[]}
        # Persist before network I/O; a crashed process must not replay a command.
        db.execute('INSERT INTO charging_batches VALUES (?,?,?,?)',(trip['id'],str(body.request_id),payload,json.dumps(pending)))
        results=await distribute_current(trip,planning,guard)
        result={'request_id':str(body.request_id),'status':'completed','vehicles':results}
        db.execute('UPDATE charging_batches SET result=? WHERE trip_id=? AND request_id=?',(json.dumps(result),trip['id'],str(body.request_id)))
        # One explicit navigation read after a successful send, never GPS polling.
        # Calculation may still be pending; unavailable fields remain unavailable.
        selected=planning.planner_id(trip)
        if any(item['user_id']==selected and item['status']=='accepted' for item in results):
            try:
                planning.active(trip['id'])
                if guard:guard()
                await fleet.fetch_navigation(selected,planning.car(trip['id'],selected))
                planning.active(trip['id'])
            except (HTTPException,httpx.HTTPError):
                pass  # command results remain saved; do not repeat the send
        await planning.broadcast(trip)
        return result


def confirm(trip_id,user_id,vehicle_id,body):
    plan=snapshot(trip_id)
    if not plan or plan['version']!=body.version or plan['current_stop']!=body.stop_index:
        raise HTTPException(409,'Die Stationsbestätigung gehört nicht zum aktuellen Routenstopp.')
    if plan['stops'][body.stop_index]['kind']!='charging':raise HTTPException(422,'Dieser Stopp ist keine Ladestation.')
    if body.preconditioning and not body.recognized:raise HTTPException(422,'Vorkonditionierung erst bestätigen, wenn die Ladestation im Tesla erkannt wurde.')
    db.execute('INSERT INTO charging_confirmations VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(trip_id,user_id) DO UPDATE SET vehicle_id=excluded.vehicle_id,version=excluded.version,stop_index=excluded.stop_index,recognized=excluded.recognized,preconditioning=excluded.preconditioning,updated_at=excluded.updated_at',
               (trip_id,user_id,vehicle_id,body.version,body.stop_index,int(body.recognized),int(body.preconditioning),time.time()))
    return snapshot(trip_id)
