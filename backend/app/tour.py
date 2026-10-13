"""Read-only live sharing and persistent, deduplicated group pause requests."""
import json
import re
import secrets
import time
import uuid
from fastapi import HTTPException
from pydantic import BaseModel, Field
from . import db, push
from .config import settings
from .security import digest


class PauseConfirm(BaseModel):
    request_ids: list[str] = Field(min_length=1, max_length=100)


def pauses(trip_id):
    return db.all_rows('SELECT r.id,r.user_id,r.created_at,u.display_name FROM toilet_requests r JOIN users u ON u.id=r.user_id JOIN members m ON m.trip_id=r.trip_id AND m.user_id=r.user_id WHERE r.trip_id=? AND r.resolved_at IS NULL AND m.left_at IS NULL ORDER BY r.created_at', (trip_id,))


def request_pause(trip, user):
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        old = connection.execute('SELECT id FROM toilet_requests WHERE trip_id=? AND user_id=? AND resolved_at IS NULL', (trip['id'],user['id'])).fetchone()
        if old:
            return {'created':False,'id':old['id']}
        request_id = str(uuid.uuid4())
        connection.execute('INSERT INTO toilet_requests VALUES (?,?,?,?,NULL)', (request_id,trip['id'],user['id'],time.time()))
    push.enqueue(trip['leader_id'], user['display_name']+' bittet um eine Toilettenpause.', '/trip/'+trip['id'], 'toilet-'+request_id, trip['id'],
                 message_key='toilet_request',parameters={'name':user['display_name']})
    return {'created':True,'id':request_id}


def confirm_pause(trip, user, request_ids):
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        pending = list(connection.execute('SELECT r.id FROM toilet_requests r JOIN members m ON m.trip_id=r.trip_id AND m.user_id=r.user_id WHERE r.trip_id=? AND r.resolved_at IS NULL AND m.left_at IS NULL', (trip['id'],)))
        selected = [row['id'] for row in pending if row['id'] in request_ids]
        if not selected:
            return None
        now = time.time()
        for request_id in selected:
            connection.execute('UPDATE toilet_requests SET resolved_at=? WHERE id=? AND resolved_at IS NULL', (now,request_id))
        message = {'id':str(uuid.uuid4()),'trip_id':trip['id'],'user_id':user['id'],'text':'Wir fahren jetzt zur Toilettenpause ab. Bitte der Gruppe folgen.',
                   'created_at':now,'kind':'toilet_departure','parameters':{}}
        connection.execute('INSERT INTO messages(id,trip_id,user_id,text,created_at,kind,parameters) VALUES (?,?,?,?,?,?,?)',
                           (message['id'],trip['id'],user['id'],message['text'],now,message['kind'],'{}'))
        recipients = list(connection.execute('SELECT user_id FROM members WHERE trip_id=? AND left_at IS NULL', (trip['id'],)))
    for row in recipients:
        push.enqueue(row['user_id'],message['text'],'/trip/'+trip['id'],'toilet-departure-'+message['id'],trip['id'],message_key='toilet_departure',parameters={})
    return message | {'display_name':user['display_name']}


def create_spectator_link(trip_id):
    key = secrets.token_urlsafe(32)
    db.execute('INSERT INTO spectator_links VALUES (?,?,?) ON CONFLICT(trip_id) DO UPDATE SET token_hash=excluded.token_hash,created_at=excluded.created_at',
               (trip_id,digest(key),time.time()))
    return {'url':settings.app_url+'/watch/'+key}


def spectator_trip(key, members):
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',key):
        raise HTTPException(404,'Zuschauerlink ist nicht mehr aktiv.')
    trip = db.one('SELECT t.* FROM spectator_links s JOIN trips t ON t.id=s.trip_id WHERE s.token_hash=?', (digest(key),))
    now = time.time()
    if not trip or trip['finished_at'] or now>=trip['ends_at']:
        raise HTTPException(404,'Zuschauerlink ist nicht mehr aktiv.')
    cars = []
    for row in members(trip['id']) if now>=trip['starts_at'] else []:
        position = row['data']
        if row['left_at'] is not None or row['role'] != 'driver' or position.get('latitude') is None:
            continue
        # Capability-scoped pseudonyms; never disclose VINs, plates, Tesla profile,
        # personal passenger GPS, chat, history, permissions or API identifiers.
        identifier=digest(key+row['id'])[:16]
        cars.append({'id':identifier,'vehicle_id':'watch-'+identifier,'display_name':row['display_name'],'vehicle_name':row['vehicle_name'],
                     'model':row['model'],'role':'driver','left_at':None,
                     'data':{k:position.get(k) for k in ('latitude','longitude','position_updated_at')}|{'source':'browser_vehicle'}})
    return {'title':trip['title'],'destination':trip['destination'],'starts_at':trip['starts_at'],'ends_at':trip['ends_at'],
            'status':'active' if now>=trip['starts_at'] else 'planned','participants':cars,'read_only':True}
