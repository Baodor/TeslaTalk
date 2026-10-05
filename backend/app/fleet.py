import asyncio
import json
import math
import time
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException
from . import db
from .config import settings
from .security import cipher

TOKEN_URL = 'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'
locks = {}


def profile_avatar(profile):
    for field in ('profile_image_url', 'picture'):
        value = profile.get(field)
        if not isinstance(value, str) or not 0 < len(value) <= 2048 or any(ord(char) < 32 for char in value):
            continue
        try:
            url = urlsplit(value)
            if url.scheme == 'https' and url.hostname and url.port in (None,443) and not url.username and not url.password:
                return value
        except ValueError:
            continue
    return None


async def token_for(user_id):
    async with locks.setdefault(user_id, asyncio.Lock()):
        row = db.one('SELECT encrypted_token FROM credentials WHERE user_id=?', (user_id,))
        if not row:
            raise HTTPException(409, 'Tesla-Konto bitte erneut verbinden.')
        token = json.loads(cipher().decrypt(row['encrypted_token'].encode()))
        if token.get('expires_at', 0) > time.time()+60:
            return token['access_token']
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(TOKEN_URL, data={'grant_type':'refresh_token', 'client_id':settings.tesla_client_id, 'refresh_token':token['refresh_token']})
        if response.status_code != 200:
            raise HTTPException(409, 'Tesla-Zugriff abgelaufen. Bitte erneut anmelden.')
        fresh = response.json()
        fresh['expires_at'] = time.time() + fresh.get('expires_in', 3600)
        fresh['refresh_token'] = fresh.get('refresh_token', token['refresh_token'])
        save_token(user_id, fresh)
        return fresh['access_token']


def save_token(user_id, token):
    token = dict(token)
    token.setdefault('expires_at', time.time()+token.get('expires_in', 3600))
    encrypted = cipher().encrypt(json.dumps(token).encode()).decode()
    db.execute('INSERT INTO credentials VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET encrypted_token=excluded.encrypted_token', (user_id,encrypted))


async def request(user_id, path, params=None):
    token = await token_for(user_id)
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(settings.fleet_url+path, headers={'Authorization':'Bearer '+token}, params=params)
    if response.status_code != 200:
        code = response.status_code
        message = {401:'Tesla-Anmeldung erneuern.', 403:'Tesla-Berechtigungen oder Partnerregistrierung fehlen.', 408:'Fahrzeug schläft oder ist nicht erreichbar.', 429:'Tesla-Anfragelimit erreicht.'}.get(code, 'Tesla-Fahrzeugdaten derzeit nicht erreichbar.')
        raise HTTPException(502, message)
    try:
        document = response.json()
    except ValueError:
        raise HTTPException(502, 'Tesla lieferte keine nutzbare API-Antwort.') from None
    if not isinstance(document, dict):
        raise HTTPException(502, 'Tesla lieferte keine nutzbare API-Antwort.')
    return document.get('response')


def object_data(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HTTPException(502, 'Tesla lieferte keine nutzbaren Fahrzeugdaten.')
    return value


def vehicle_model(configuration, fallback='Tesla'):
    code = object_data(configuration).get('car_type')
    if not isinstance(code, str):
        return fallback
    names = {'3':'Model 3', 'model3':'Model 3', 'y':'Model Y', 'modely':'Model Y',
             's':'Model S', 'models':'Model S', 'models2':'Model S',
             'x':'Model X', 'modelx':'Model X', 'modelx2':'Model X', 'cybertruck':'Cybertruck'}
    return names.get(code.strip().lower(), fallback)


async def synchronize(user_id):
    user = db.one('SELECT * FROM users WHERE id=?', (user_id,))
    if user['provider'] == 'demo':
        return db.all_rows('SELECT * FROM vehicles WHERE user_id=?', (user_id,))
    items = await request(user_id, '/api/1/vehicles')
    if not isinstance(items, list):
        raise HTTPException(502, 'Tesla lieferte keine Fahrzeugliste.')
    with db.connect() as connection:
        for item in items:
            item = object_data(item)
            vin = item.get('vin')
            if not vin:
                continue
            # Only basic own-vehicle details; never return tokens or Tesla profile data.
            existing = connection.execute('SELECT user_id,model FROM vehicles WHERE id=?', (vin,)).fetchone()
            if existing and existing['user_id'] != user_id:
                # Shared Tesla vehicles can occur in several accounts. Use owner-scoped IDs.
                vin = user_id+':'+vin
                existing = connection.execute('SELECT user_id,model FROM vehicles WHERE id=?', (vin,)).fetchone()
            model = vehicle_model(item.get('vehicle_config'), existing['model'] if existing else 'Tesla')
            connection.execute('INSERT INTO vehicles(id,user_id,name,model) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,model=excluded.model', (vin,user_id,item.get('display_name') or 'Mein Tesla',model))
        vehicles = connection.execute('SELECT * FROM vehicles WHERE user_id=?', (user_id,)).fetchall()
        if vehicles and not user['favorite_vehicle']:
            connection.execute('UPDATE users SET favorite_vehicle=? WHERE id=?', (vehicles[0]['id'], user_id))
    return [dict(row) for row in vehicles]


def normalize(payload):
    if not isinstance(payload, dict):
        raise HTTPException(502, 'Tesla lieferte keine nutzbaren Fahrzeugdaten.')
    payload = object_data(payload)
    drive = object_data(payload.get('drive_state'))
    charge = object_data(payload.get('charge_state'))
    state = object_data(payload.get('vehicle_state'))
    def number(section, field):
        value = section.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value)):
            raise HTTPException(502, 'Tesla lieferte keine nutzbaren Fahrzeugdaten.')
        return value
    speed, battery_range, odometer = number(drive,'speed'), number(charge,'battery_range'), number(state,'odometer')
    return {
        'latitude': number(drive,'latitude'), 'longitude': number(drive,'longitude'),
        'speed_kmh': None if speed is None else round(speed*1.609344, 1),
        'heading': number(drive,'heading'), 'battery_pct':number(charge,'battery_level'),
        'range_km':None if battery_range is None else round(battery_range*1.609344,1),
        'odometer_km':None if odometer is None else round(odometer*1.609344,3),
        'source':'fleet', 'updated_at':time.time(),
    }


async def fetch_vehicle(user_id, vehicle):
    cached = json.loads(vehicle['data'])
    if time.time()-cached.get('fleet_fetched_at', 0) < 60:
        return cached
    user = db.one('SELECT * FROM users WHERE id=?', (user_id,))
    if user['provider'] == 'demo':
        return cached
    vin = vehicle['id'].split(':')[-1]
    payload = await request(user_id, f'/api/1/vehicles/{vin}/vehicle_data', {'endpoints':'charge_state;drive_state;location_data;vehicle_state;vehicle_config'})
    data = normalize(payload)
    data['fleet_fetched_at'] = time.time()
    model = vehicle_model(payload.get('vehicle_config'),vehicle['model'])
    db.execute('UPDATE vehicles SET data=?,model=? WHERE id=?', (json.dumps(data), model, vehicle['id']))
    return data
