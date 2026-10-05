"""Opt-in comfort commands. No arbitrary endpoints, locks or automatic retries."""
import asyncio
import json
import math
import ssl
import sqlite3
import time
from typing import Literal
from uuid import UUID
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import db, fleet
from .config import settings
from .security import limiter

Action = Literal['frunk_open','rear_trunk_toggle','windows_vent','windows_close','climate_on','climate_off']
COMMANDS = {
    'frunk_open': ('actuate_trunk', {'which_trunk':'front'}),
    'rear_trunk_toggle': ('actuate_trunk', {'which_trunk':'rear'}),
    'windows_vent': ('window_control', {'command':'vent'}),
    'windows_close': ('window_control', {'command':'close'}),
    'climate_on': ('auto_conditioning_start', {}),
    'climate_off': ('auto_conditioning_stop', {}),
}


class ControlBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    action: Action
    vehicle_ids: list[str] = Field(min_length=1,max_length=100)

    @field_validator('vehicle_ids')
    @classmethod
    def unique_vehicles(cls, value):
        if len(set(value)) != len(value) or any(not item or len(item)>120 for item in value):
            raise ValueError('Eindeutige Fahrzeug-IDs erforderlich.')
        return value


def overview(trip_id):
    rows = db.all_rows("SELECT m.user_id,m.vehicle_id,u.display_name,u.provider,v.name AS vehicle_name,g.granted_at FROM members m JOIN users u ON u.id=m.user_id JOIN vehicles v ON v.id=m.vehicle_id AND v.user_id=m.user_id LEFT JOIN control_grants g ON g.trip_id=m.trip_id AND g.user_id=m.user_id AND g.vehicle_id=m.vehicle_id WHERE m.trip_id=? AND m.role='driver' AND m.left_at IS NULL AND u.provider!='guest'",(trip_id,))
    for row in rows:
        row['demo'] = row.pop('provider') == 'demo'
        row['available'] = row['demo'] or settings.group_controls_ready
        row['allowed'] = row.pop('granted_at') is not None
    return {'vehicles':rows,'configured':settings.group_controls_ready,'actions':list(COMMANDS)}


def current_car(trip_id,user_id):
    row = db.one("SELECT v.*,u.provider FROM members m JOIN users u ON u.id=m.user_id JOIN vehicles v ON v.id=m.vehicle_id AND v.user_id=m.user_id WHERE m.trip_id=? AND m.user_id=? AND m.role='driver' AND m.left_at IS NULL AND u.provider!='guest'",(trip_id,user_id))
    if not row:
        raise HTTPException(403,'Nur Fahrer mit eigenem ausgewähltem Fahrzeug können die Komfortsteuerung freigeben.')
    return row


def command_access(trip_id,leader_id,user_id,vehicle_id):
    now = time.time()
    trip = db.one('SELECT * FROM trips WHERE id=?',(trip_id,))
    if not trip or trip['leader_id'] != leader_id or trip['finished_at'] or not trip['starts_at'] <= now < trip['ends_at']:
        raise HTTPException(403,'Die Fahrt oder Leitung ist nicht mehr aktiv.')
    car = current_car(trip_id,user_id)
    grant = db.one('SELECT vehicle_id FROM control_grants WHERE trip_id=? AND user_id=?',(trip_id,user_id))
    if car['id'] != vehicle_id or not grant or grant['vehicle_id'] != vehicle_id:
        raise HTTPException(403,'Die Freigabe für dieses Fahrzeug wurde widerrufen oder das Fahrzeug gewechselt.')
    return car


def parked(payload):
    drive = payload.get('drive_state')
    if not isinstance(drive,dict) or 'shift_state' not in drive:
        return False
    # Tesla reports null for Park on some models. Require an explicit speed too.
    speed = drive.get('speed')
    stamp = drive.get('timestamp')
    return (drive['shift_state'] in (None,'P') and 'speed' in drive and
            (speed is None or not isinstance(speed,bool) and isinstance(speed,(int,float)) and speed == 0) and
            not isinstance(stamp,bool) and isinstance(stamp,(int,float)) and math.isfinite(stamp) and
            -5 <= time.time()-stamp/1000 <= 30)


async def send_one(trip_id,leader_id,row,action,authorize):
    user_id, vehicle_id = row['user_id'], row['vehicle_id']
    async with fleet.vehicle_lock(user_id,vehicle_id):
        authorize()
        car = command_access(trip_id,leader_id,user_id,vehicle_id)
        if car['provider'] == 'demo':
            return 'demo','Simuliert; kein echter Fahrzeugbefehl gesendet.'
        if not settings.group_controls_ready:
            raise HTTPException(503,'Die signierte Tesla-Befehlsanbindung ist noch nicht eingerichtet.')
        vin = quote(vehicle_id.split(':')[-1],safe='')
        if action in ('frunk_open','rear_trunk_toggle','windows_vent','windows_close'):
            payload = fleet.object_data(await fleet.request(user_id,f'/api/1/vehicles/{vin}/vehicle_data',{'endpoints':'drive_state;vehicle_state;location_data'}))
            authorize()
            command_access(trip_id,leader_id,user_id,vehicle_id)
            if not parked(payload):
                return 'skipped','Parkstellung und Stillstand konnten nicht aktuell bestätigt werden.'
            state = fleet.object_data(payload.get('vehicle_state'))
            if action in ('frunk_open','rear_trunk_toggle'):
                field = 'ft' if action == 'frunk_open' else 'rt'
                stamp = state.get('timestamp')
                if not isinstance(stamp,(int,float)) or isinstance(stamp,bool) or not math.isfinite(stamp) or not -5 <= time.time()-stamp/1000 <= 30 or state.get(field) not in (0,255) or isinstance(state.get(field),bool):
                    return 'skipped','Aktuelle Kofferraumposition ist nicht eindeutig bekannt.'
                if action == 'frunk_open' and state[field] != 0:
                    return 'skipped','Frunk ist bereits offen.'
        token = await fleet.token_for(user_id)
        name, body = COMMANDS[action]
        verify = ssl.create_default_context(cafile=settings.command_proxy_ca) if settings.command_proxy_ca else True
        async with httpx.AsyncClient(timeout=25,verify=verify,follow_redirects=False) as client:
            # Recheck after every upstream await, immediately before dispatch.
            authorize()
            command_access(trip_id,leader_id,user_id,vehicle_id)
            if action in ('frunk_open','rear_trunk_toggle','windows_vent','windows_close') and not parked(payload):
                return 'skipped','Parkdaten sind inzwischen zu alt; kein Befehl gesendet.'
            response = await client.post(settings.command_proxy_url+f'/api/1/vehicles/{vin}/command/{name}',headers={'Authorization':'Bearer '+token},json=body)
        if response.status_code != 200:
            message = {401:'Tesla-Konto erneut verbinden.',403:'vehicle_cmds oder der virtuelle Fahrzeugschlüssel fehlt.',408:'Fahrzeug nicht erreichbar; Ergebnis bitte am Auto prüfen.',429:'Tesla-Anfragelimit erreicht.'}.get(response.status_code,'Tesla hat den Befehl nicht bestätigt; Ergebnis bitte am Auto prüfen.')
            return 'unknown' if response.status_code >= 500 or response.status_code == 408 else 'error',f'Tesla/Proxy HTTP {response.status_code}: {message}'
        try:
            document = response.json()
            result = document.get('response') if isinstance(document,dict) else None
        except ValueError:
            result = None
        if not isinstance(result,dict) or not isinstance(result.get('result'),bool):
            return 'unknown','Keine eindeutige Bestätigung; bitte am Auto prüfen, nicht automatisch wiederholen.'
        if not result['result']:
            return 'error','Fahrzeug hat den Befehl abgelehnt oder unterstützt ihn nicht.'
        return 'accepted','Von Tesla bestätigt; den tatsächlichen Zustand am Auto prüfen.'


def recover_interrupted():
    # Never replay a trunk/window command when a worker restarted mid-request.
    for row in db.all_rows("SELECT trip_id,request_id,result FROM control_batches WHERE status='running'"):
        result = json.loads(row['result'])
        result['status'] = 'completed'
        for item in result['vehicles']:
            if item['status'] == 'pending':
                item.update(status='unknown',message='Server wurde unterbrochen; Ergebnis am Auto prüfen. Kein automatischer Wiederholungsversuch.')
        db.execute("UPDATE control_batches SET status='completed',result=? WHERE trip_id=? AND request_id=?",(json.dumps(result),row['trip_id'],row['request_id']))


async def execute(trip_id,leader_id,body,authorize):
    authorize()
    request_id = str(body.request_id)
    payload = json.dumps({'action':body.action,'vehicle_ids':sorted(body.vehicle_ids)},sort_keys=True)
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing = connection.execute('SELECT * FROM control_batches WHERE trip_id=? AND request_id=?',(trip_id,request_id)).fetchone()
        if existing:
            if existing['leader_id'] != leader_id or existing['payload'] != payload:
                raise HTTPException(409,'Diese Auftrags-ID wurde bereits für eine andere Aktion verwendet.')
            return json.loads(existing['result'])
        if connection.execute("SELECT request_id FROM control_batches WHERE trip_id=? AND status='running'",(trip_id,)).fetchone():
            raise HTTPException(409,'Eine Gruppenaktion läuft bereits. Bitte auf deren Ergebnis warten.')
        rows = {row['vehicle_id']:row for row in overview(trip_id)['vehicles'] if row['allowed']}
        if any(vehicle not in rows for vehicle in body.vehicle_ids):
            raise HTTPException(409,'Fahrzeugliste oder Freigaben haben sich geändert. Bitte die Übersicht aktualisieren.')
        limiter.check(('comfort-command',leader_id),6,60)
        selected = [rows[vehicle] for vehicle in body.vehicle_ids]
        result = {'request_id':request_id,'action':body.action,'status':'running','vehicles':[
            {key:row[key] for key in ('user_id','vehicle_id','display_name','vehicle_name','demo')} | {'status':'pending','message':'Ergebnis steht noch aus; denselben Auftrag nicht erneut auslösen.'} for row in selected]}
        connection.execute('INSERT INTO control_batches VALUES (?,?,?,?,?,?,?)',(trip_id,request_id,leader_id,payload,json.dumps(result),'running',time.time()))
    gate = asyncio.Semaphore(4)
    async def run(row,item):
        async with gate:
            try:
                status,message = await send_one(trip_id,leader_id,row,body.action,authorize)
            except HTTPException as error:
                status,message = 'error',error.detail
            except httpx.HTTPError:
                status,message = 'unknown','Verbindung unterbrochen; Ergebnis am Auto prüfen. Kein automatischer Wiederholungsversuch.'
            except (OSError,ValueError,sqlite3.IntegrityError):
                status,message = 'error','Die Tesla-Befehlsanbindung ist derzeit nicht nutzbar.'
            item.update(status=status,message=message)
            db.execute('UPDATE control_batches SET result=? WHERE trip_id=? AND request_id=?',(json.dumps(result),trip_id,request_id))
    await asyncio.gather(*(run(row,item) for row,item in zip(selected,result['vehicles'])))
    result['status'] = 'completed'
    db.execute("UPDATE control_batches SET status='completed',result=? WHERE trip_id=? AND request_id=?",(json.dumps(result),trip_id,request_id))
    return result
