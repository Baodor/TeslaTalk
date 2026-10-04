import asyncio
import json
import time
import httpx
from fastapi import HTTPException
from . import db
from .config import settings
from .security import cipher

TOKEN_URL = 'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'
locks = {}


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
    return response.json().get('response')


async def synchronize(user_id):
    user = db.one('SELECT * FROM users WHERE id=?', (user_id,))
    if user['provider'] == 'demo':
        return db.all_rows('SELECT * FROM vehicles WHERE user_id=?', (user_id,))
    items = await request(user_id, '/api/1/vehicles')
    if not isinstance(items, list):
        raise HTTPException(502, 'Tesla lieferte keine Fahrzeugliste.')
    with db.connect() as connection:
        for item in items:
            vin = item.get('vin')
            if not vin:
                continue
            # Only basic own-vehicle details; never return tokens or Tesla profile data.
            model = 'Model '+str(item.get('vehicle_config', {}).get('car_type', '3')).upper()
            existing = connection.execute('SELECT user_id FROM vehicles WHERE id=?', (vin,)).fetchone()
            if existing and existing['user_id'] != user_id:
                # Shared Tesla vehicles can occur in several accounts. Use owner-scoped IDs.
                vin = user_id+':'+vin
            connection.execute('INSERT INTO vehicles(id,user_id,name,model) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name', (vin,user_id,item.get('display_name') or 'Mein Tesla',model))
        vehicles = connection.execute('SELECT * FROM vehicles WHERE user_id=?', (user_id,)).fetchall()
        if vehicles and not user['favorite_vehicle']:
            connection.execute('UPDATE users SET favorite_vehicle=? WHERE id=?', (vehicles[0]['id'], user_id))
    return [dict(row) for row in vehicles]


def normalize(payload):
    drive = payload.get('drive_state') or {}
    charge = payload.get('charge_state') or {}
    state = payload.get('vehicle_state') or {}
    return {
        'latitude': drive.get('latitude'), 'longitude': drive.get('longitude'),
        'speed_kmh': None if drive.get('speed') is None else round(drive['speed']*1.609344, 1),
        'heading': drive.get('heading'), 'battery_pct':charge.get('battery_level'),
        'range_km':None if charge.get('battery_range') is None else round(charge['battery_range']*1.609344,1),
        'odometer_km':None if state.get('odometer') is None else round(state['odometer']*1.609344,3),
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
    model = (payload.get('vehicle_config') or {}).get('car_type')
    db.execute('UPDATE vehicles SET data=?,model=? WHERE id=?', (json.dumps(data), 'Model '+str(model).upper() if model else vehicle['model'], vehicle['id']))
    return data
