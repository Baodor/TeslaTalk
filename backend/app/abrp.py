"""Iternio v2 integration, based on its published OpenAPI 2.0.3 contract.

Only fixed provider endpoints are contacted. Planning is explicit, quota-bound
and persisted before I/O; retries of a request UUID never create another plan.
"""
import asyncio
import base64
import json
import math
import time
import uuid
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from . import db, charging_plans
from .config import settings
from .security import cipher

BASE='https://api.iternio.com/2'
cache={}
locks={}

class AccountLogin(BaseModel):
    username:str=Field(min_length=1,max_length=200)
    password:SecretStr=Field(min_length=1,max_length=1000)

class PlanLink(BaseModel):
    url:str=Field(min_length=1,max_length=2000)

class Destination(BaseModel):
    model_config=ConfigDict(extra='forbid')
    value:str=Field(min_length=1,max_length=300)
    stay_minutes:int=Field(default=0,ge=0,le=1440)
    charger_id:int|None=Field(default=None,gt=0)
    def wire(self):
        value=self.value.strip()
        if not value:raise HTTPException(422,'Bitte Start, Ziel und Zwischenstopps vollständig angeben.')
        location={'type':'ADDRESS','value':value}
        if self.charger_id:location={'type':'CHARGER_ID','value':self.charger_id}
        else:
            parts=value.split(',')
            if len(parts)==2:
                try:
                    lat,lon=map(float,parts)
                    if not math.isfinite(lat+lon) or not -90<=lat<=90 or not -180<=lon<=180:raise HTTPException(422,'Ungültige Planungskoordinaten.')
                    location={'type':'COORDINATES','lat':lat,'long':lon}
                except ValueError:pass  # ordinary addresses may contain a comma
        return {'location':location,'name':value,'timeSettings':{'stayForSeconds':self.stay_minutes*60}}

class Calculate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:uuid.UUID
    planner_user_id:str=Field(min_length=1,max_length=80)
    typecode:str=Field(min_length=1,max_length=150,pattern=r'^[A-Za-z0-9:_\-.]+$')
    departure_soc:float=Field(ge=1,le=100,allow_inf_nan=False)
    arrival_soc:float=Field(default=10,ge=1,le=80,allow_inf_nan=False)
    network_ids:list[int]=Field(default_factory=list,max_length=30)
    exclusive:bool=False
    destinations:list[Destination]=Field(min_length=2,max_length=25)
    costs_confirmed:bool=False


def ready():
    if not settings.abrp_api_key:raise HTTPException(503,'Der Betreiber muss zuerst den Iternio-Planning-Zugang einrichten.')


def account(user_id):
    row=db.one('SELECT * FROM abrp_accounts WHERE user_id=?',(user_id,))
    if not row or row['expires_at']<=time.time():return None
    return json.loads(cipher().decrypt(row['encrypted_session'].encode()))


def account_status(user_id):
    current=account(user_id)
    return {'configured':bool(settings.abrp_api_key),'connected':bool(current),'username':current['username'] if current else None,
            'expires_at':current['expires_at'] if current else None,'daily_limit':settings.abrp_daily_limit}


async def request(method,path,body=None,params=None,session=None):
    ready()
    headers={'X-API-KEY':settings.abrp_api_key}
    if session:headers['X-ABRP-SESSION']=session
    try:
        async with httpx.AsyncClient(timeout=60 if path=='/plan' else 15,follow_redirects=False) as client:
            async with client.stream(method,BASE+path,headers=headers,json=body,params=params) as response:
                if response.status_code!=200:
                    if response.status_code in (401,403):raise HTTPException(409,'Iternio hat den Zugang abgelehnt. ABRP-Verbindung und Planning-API-Freigabe prüfen.')
                    if response.status_code==404:raise HTTPException(404,'Der ABRP-Plan oder die Station wurde nicht gefunden.')
                    if response.status_code==429:raise HTTPException(429,'Iternio-Anfragelimit erreicht. Bitte später erneut versuchen.')
                    raise HTTPException(502,'Iternio konnte die Anfrage nicht abschließen. Eine Berechnung wird nicht automatisch wiederholt.')
                data=bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>8_000_000:raise HTTPException(502,'Iternio-Antwort ist zu groß.')
                result=json.loads(data)
                if not isinstance(result,dict):raise ValueError()
                return result
    except HTTPException:raise
    except (httpx.HTTPError,ValueError):
        raise HTTPException(502,'Iternio ist nicht erreichbar oder lieferte eine ungültige Antwort. Eine Berechnung wird nicht automatisch wiederholt.') from None


async def connect(user_id,body,guard=None):
    data=await request('POST','/auth/login',{'username':body.username,'password':body.password.get_secret_value()})
    token=data.get('access_token');duration=data.get('expires_in')
    if not isinstance(token,str) or not token.strip() or not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 0<duration<=31_536_000:
        raise HTTPException(502,'Iternio lieferte keine gültige Kontositzung.')
    if guard:guard()
    expiry=time.time()+duration
    # No password or refresh token is stored; no undocumented refresh calls.
    stored={'token':token,'username':body.username,'expires_at':expiry}
    db.execute('INSERT INTO abrp_accounts VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET encrypted_session=excluded.encrypted_session,expires_at=excluded.expires_at',
               (user_id,cipher().encrypt(json.dumps(stored).encode()).decode(),expiry))
    cache.pop(('models',user_id),None)
    return account_status(user_id)


async def catalog(user_id):
    ready();now=time.time()
    network=cache.get(('networks',))
    if not network or network[0]<now:
        items=[];cursor=None
        for _ in range(10):
            data=await request('GET','/network',params={'limit':1000,**({'cursor':cursor} if cursor else {})})
            items.extend(data.get('items') or [])
            meta=data.get('meta') or {};next_cursor=meta.get('endCursor')
            if not meta.get('hasNextPage') or not next_cursor or next_cursor==cursor:break
            cursor=next_cursor
        else:raise HTTPException(502,'Iternio-Ladenetzliste ist zu groß. Bitte später erneut versuchen.')
        cleaned=[{'id':int(row['id']),'name':str(row['name'])[:150]} for row in items if isinstance(row,dict) and not row.get('deprecated') and isinstance(row.get('id'),int) and row['id']>0 and isinstance(row.get('name'),str)]
        network=(now+1800,cleaned);cache[('networks',)]=network
    current=account(user_id);models=[]
    if current:
        old=cache.get(('models',user_id))
        if not old or old[0]<now:
            data=await request('GET','/vehicle/_list',session=current['token'])
            models=[{'typecode':row['typecode'],'title':str(row.get('title') or row['typecode'])[:200],'manufacturer':str(row.get('manufacturer',''))[:80],'model':str(row.get('model',''))[:150]}
                    for row in (data.get('vehicles') or []) if isinstance(row,dict) and isinstance(row.get('typecode'),str)]
            old=(min(now+1800,current['expires_at']),models);cache[('models',user_id)]=old
        models=old[1]
    return account_status(user_id)|{'networks':network[1],'models':models}


def plan_id(value):
    try:
        parsed=urlparse(value.strip())
        if parsed.scheme not in ('https','http') or parsed.hostname not in ('abetterrouteplanner.com','www.abetterrouteplanner.com','web.abetterrouteplanner.com') or parsed.username or parsed.password:
            raise ValueError()
        values=parse_qs(parsed.query)
        identifiers=values.get('plan_uuid') or values.get('plan_id') or values.get('planId')
        if not identifiers or len(identifiers)!=1:raise ValueError()
        return str(uuid.UUID(identifiers[0]))
    except (ValueError,TypeError):raise HTTPException(422,'Bitte einen ABRP-Teilen-Link mit Plan-ID einsetzen; Kurzlinks werden nicht automatisch geöffnet.') from None


async def prepare_link(user_id,body):
    current=account(user_id)
    if not current:raise HTTPException(409,'Für den ABRP-Linkabruf zuerst das ABRP-Konto verbinden.')
    saved=await request('GET','/abrp/plan/'+plan_id(body.url)+'/request',session=current['token'])
    try:return link_parameters(saved)
    except HTTPException:raise
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError):
        raise HTTPException(502,'Der gespeicherte ABRP-Plan enthält ungültige Planungsparameter.') from None


def link_parameters(saved):
    original=saved.get('request') or {};destinations=[]
    for item in original.get('destinations') or []:
        location=item.get('location') or {};kind=location.get('type');value=location.get('value')
        if kind=='COORDINATES':value=f"{location['lat']}, {location['long']}"
        elif kind=='CHARGER_ID':value=item.get('name') or 'Ladestation '+str(value)
        elif kind!='ADDRESS':raise HTTPException(502,'Der gespeicherte ABRP-Plan enthält ein nicht unterstütztes Ziel.')
        destinations.append({'value':str(value),'charger_id':location.get('value') if kind=='CHARGER_ID' else None,
                             'stay_minutes':min(1440,max(0,int((item.get('timeSettings') or {}).get('stayForSeconds',0)/60)))})
    vehicle=original.get('vehicle') or {};charging=original.get('charging') or {}
    if not 2<=len(destinations)<=25:raise HTTPException(502,'Der gespeicherte ABRP-Plan enthält keine gültige Zielliste.')
    result={'destinations':destinations,'typecode':saved.get('typecode') or (vehicle.get('identifier') or {}).get('value'),
            'departure_soc':float(vehicle.get('currentSocFrac',.9))*100,'arrival_soc':float(charging.get('minimumDestinationSocFrac',.1))*100,
            'network_ids':[row['id'] for row in charging.get('networkPreferences',[]) if row.get('preference') in ('EXCLUSIVE','PREFER','PREFER_STRONGLY')],
            'exclusive':any(row.get('preference')=='EXCLUSIVE' for row in charging.get('networkPreferences',[])),
            'original_plan_id':saved.get('planId'),'kind':'parameters_only',
            'notice':'Start, Ziele, Fahrzeug, Akku und ausgewählte Ladenetze wurden übernommen. Weitere ABRP-Einstellungen bleiben in ABRP. Eine neue Berechnung kann vom gespeicherten Plan abweichen.'}
    # Apply the same bounded form contract before exposing provider parameters.
    checked=Calculate(request_id=uuid.uuid4(),planner_user_id='link',**{key:result[key] for key in ('destinations','typecode','departure_soc','arrival_soc','network_ids','exclusive')})
    result.update({key:checked.model_dump(mode='json')[key] for key in ('destinations','typecode','departure_soc','arrival_soc','network_ids','exclusive')})
    return result


def points(polyline):
    value=polyline.get('value');precision=polyline.get('precision')
    if not isinstance(value,str) or len(value)>200_000 or precision not in (5,6):raise ValueError()
    # Reuse the bounded Tesla polyline decoder after precision normalization.
    from .navigation import decode_route_line
    decoded=decode_route_line(base64.b64encode(value.encode()).decode())
    if precision==5:decoded=[(round(lat*10,5),round(lon*10,5)) for lat,lon in decoded]
    if any(not -90<=lat<=90 or not -180<=lon<=180 for lat,lon in decoded):raise ValueError()
    return decoded


async def normalize(data,title):
    routes=data.get('routes') or []
    if not routes:raise HTTPException(422,'Iternio findet mit diesen Vorgaben keine fahrbare Route.')
    route=routes[0];legs=route.get('legs') or []
    if not 2<=len(legs)<=51:raise HTTPException(502,'Iternio lieferte keine vollständige Stoppfolge.')
    stops=[];geometry=[]
    try:
        origins=[leg['origin'] for leg in legs]
        for index,origin in enumerate(origins):
            charger=origin.get('charger') or {};charger_id=charger.get('id')
            stop={'name':origin['name'],'latitude':origin['lat'],'longitude':origin['long'],
                  'kind':'charging' if charger_id else 'destination' if index==len(origins)-1 else 'waypoint',
                  'operator':'','address':'','google_place_id':None,'charger_id':charger_id,
                  'arrival_soc':origin['arrivalSocFrac']*100 if origin.get('arrivalSocFrac') is not None else None,'departure_soc':origin['departureSocFrac']*100 if origin.get('departureSocFrac') is not None else None,
                  'charge_minutes':origin['chargeDurationSec']/60 if origin.get('chargeDurationSec') is not None else None}
            if index:stops.append(stop)
            else:origin_stop=stop
            line=(legs[index].get('driveDetails') or {}).get('polyline')
            if line and line.get('value'):
                segment=points(line);geometry.extend(segment[1:] if geometry and segment and geometry[-1]==segment[0] else segment)
            if len(geometry)>20000:raise ValueError()
        ids=list(dict.fromkeys(stop['charger_id'] for stop in stops if stop['charger_id']))
        if ids:
            try:references=(await request('POST','/charger/_google-place-ids',{'chargerIds':ids})).get('chargerToGoogle') or {}
            except HTTPException:references={}
            if not isinstance(references,dict):references={}
            limit=asyncio.Semaphore(4)
            async def enrich(stop):
                if not stop['charger_id']:return
                reference=references.get(str(stop['charger_id']))
                import re
                if isinstance(reference,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,256}',reference):stop['google_place_id']=reference
                try:
                    async with limit:detail=await request('GET','/charger/'+str(stop['charger_id']))
                    if detail.get('id')!=stop['charger_id']:return
                    stop['operator']=str((detail.get('network') or {}).get('name',''))[:100]
                    network_id=(detail.get('network') or {}).get('id')
                    if isinstance(network_id,int) and network_id>0:stop['network_id']=network_id
                except (HTTPException,TypeError,AttributeError):pass  # retain paid route when optional metadata is unavailable or malformed
            await asyncio.gather(*(enrich(stop) for stop in stops))
        summary=route.get('summary') or {}
        return charging_plans.Plan(title=title,stops=stops,origin=origin_stop,route_points=geometry,source='abrp',
                                   distance_km=float(summary['distanceM'])/1000,duration_minutes=float(summary['durationSec'])/60).model_dump()
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError):
        raise HTTPException(502,'Iternio lieferte eine ungültige Route. Es werden keine Ladehalte geraten.') from None


async def calculate(trip,body,guard):
    ready()
    if not body.costs_confirmed:raise HTTPException(422,'Die mögliche kostenpflichtige Iternio-Berechnung zuerst bestätigen.')
    from . import route_planning
    vehicle=route_planning.car(trip['id'],body.planner_user_id)
    payload=json.dumps(body.model_dump(mode='json')|{'vehicle_id':vehicle['id']},sort_keys=True)
    gate=locks.setdefault(trip['id'],asyncio.Lock())
    async with gate:
        guard()
        previous=db.one('SELECT payload,result FROM abrp_requests WHERE trip_id=? AND request_id=?',(trip['id'],str(body.request_id)))
        if previous:
            if previous['payload']!=payload:raise HTTPException(409,'Diese Auftrags-ID gehört zu einer anderen ABRP-Berechnung.')
            return json.loads(previous['result'])
        networks=(await catalog(trip['leader_id']))['networks'] if body.network_ids else []
        if not set(body.network_ids)<={row['id'] for row in networks} or any(value<=0 for value in body.network_ids):raise HTTPException(422,'Bitte gültige Ladenetze aus der Liste auswählen.')
        wire={'destinations':[item.wire() for item in body.destinations],
              'vehicle':{'identifier':{'type':'TYPECODE','value':body.typecode},'currentSocFrac':body.departure_soc/100},
              'charging':{'minimumDestinationSocFrac':body.arrival_soc/100,'networkPreferences':[{'id':value,'preference':'EXCLUSIVE' if body.exclusive else 'PREFER'} for value in dict.fromkeys(body.network_ids)]}}
        if body.exclusive and not body.network_ids:raise HTTPException(422,'Für ausschließliches Laden mindestens ein Ladenetz auswählen.')
        guard()
        day=datetime.now(ZoneInfo(settings.timezone)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        with db.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if connection.execute('SELECT count(*) FROM abrp_requests WHERE created_at>=?',(day,)).fetchone()[0]>=settings.abrp_daily_limit:
                raise HTTPException(429,'Das tägliche Iternio-Planungslimit dieser Instanz ist erreicht.')
            pending={'request_id':str(body.request_id),'status':'unknown','plan':None}
            connection.execute('INSERT INTO abrp_requests VALUES (?,?,?,?,?,?)',(trip['id'],str(body.request_id),trip['leader_id'],payload,json.dumps(pending),time.time()))
        try:
            data=await request('POST','/plan',wire)
            guard()
            if route_planning.car(trip['id'],body.planner_user_id)['id']!=vehicle['id']:raise HTTPException(409,'Das Planungsfahrzeug wurde gewechselt. Berechnung bitte prüfen.')
            plan=await normalize(data,trip['title'])
            guard()
            result={'request_id':str(body.request_id),'status':'completed','plan':plan,'provider_plan_id':data.get('planId')}
            db.execute('UPDATE abrp_requests SET result=? WHERE trip_id=? AND request_id=?',(json.dumps(result,ensure_ascii=False),trip['id'],str(body.request_id)))
            return result
        except HTTPException as error:
            # Never retry a charged plan, including after a post-processing failure.
            result={'request_id':str(body.request_id),'status':'unknown' if error.status_code>=500 else 'error','plan':None,'message':error.detail}
            db.execute('UPDATE abrp_requests SET result=? WHERE trip_id=? AND request_id=?',(json.dumps(result,ensure_ascii=False),trip['id'],str(body.request_id)))
            raise
