import asyncio
import json
import math
import ssl
import time
from urllib.parse import quote, urlsplit
import httpx
from fastapi import HTTPException
from . import db
from .config import settings
from .security import cipher
from .navigation import from_fleet, demo_navigation, empty_navigation, TELEMETRY_MAX_AGE

TOKEN_URL = 'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'
locks = {}
vehicle_locks = {}


def vehicle_lock(user_id, vehicle_id):
    return vehicle_locks.setdefault((user_id, vehicle_id), asyncio.Lock())


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
        'navigation':from_fleet(drive),
    }


async def fetch_vehicle(user_id, vehicle):
    async with vehicle_lock(user_id, vehicle['id']):
        # Re-read inside the lock: concurrent polling/manual refresh must share
        # the cache and cannot overwrite a newer telemetry import.
        vehicle = db.one('SELECT * FROM vehicles WHERE id=? AND user_id=?', (vehicle['id'],user_id)) or vehicle
        return await _fetch_vehicle(user_id, vehicle)


async def _fetch_vehicle(user_id, vehicle):
    cached = json.loads(vehicle['data'])
    if time.time()-cached.get('fleet_fetched_at', 0) < 60:
        return cached
    user = db.one('SELECT * FROM users WHERE id=?', (user_id,))
    if user['provider'] == 'demo':
        navigation = cached.get('navigation')
        if not navigation or navigation.get('source') == 'telemetry' and time.time()-navigation['updated_at'] > TELEMETRY_MAX_AGE:
            navigation = demo_navigation()
        return cached | {'navigation':navigation}
    vin = vehicle['id'].split(':')[-1]
    payload = await request(user_id, f'/api/1/vehicles/{vin}/vehicle_data', {'endpoints':'charge_state;drive_state;location_data;vehicle_state;vehicle_config'})
    data = normalize(payload)
    telemetry = cached.get('navigation') or {}
    if telemetry.get('source') == 'telemetry' and time.time()-telemetry.get('updated_at',0) <= TELEMETRY_MAX_AGE:
        # A configured stream is more complete than polling (RouteLine). Keep
        # its recent snapshot while still refreshing the ordinary car metrics.
        data['navigation'] = telemetry
    data['fleet_fetched_at'] = time.time()
    model = vehicle_model(payload.get('vehicle_config'),vehicle['model'])
    db.execute('UPDATE vehicles SET data=?,model=? WHERE id=?', (json.dumps(data), model, vehicle['id']))
    return data


async def fetch_navigation(user_id, vehicle):
    current = db.one('SELECT * FROM vehicles WHERE id=? AND user_id=?', (vehicle['id'],user_id)) or vehicle
    cached = json.loads(current['data']).get('navigation')
    if cached and cached.get('source') == 'telemetry' and time.time()-cached['updated_at'] <= TELEMETRY_MAX_AGE:
        return cached
    return (await fetch_vehicle(user_id, current)).get('navigation') or empty_navigation()


def navigation_command_access(trip_id,user_id,vehicle_id):
    row = db.one('SELECT t.*,m.vehicle_id,m.left_at FROM trips t JOIN members m ON m.trip_id=t.id AND m.user_id=? WHERE t.id=?',(user_id,trip_id))
    if not row or row['left_at'] is not None or row['vehicle_id'] != vehicle_id or row['finished_at'] or not row['starts_at'] <= time.time() < row['ends_at']:
        raise HTTPException(403,'Fahrt oder Fahrzeugfreigabe ist nicht mehr aktiv.')
    if row['leader_id'] != user_id and not db.one('SELECT user_id FROM route_followers WHERE trip_id=? AND user_id=? AND vehicle_id=?',(trip_id,user_id,vehicle_id)):
        raise HTTPException(403,'Dieser Fahrer hat die Zielübernahme nicht erlaubt.')


async def send_navigation(user_id, vehicle, destination, trip_id):
    """Only navigation_request, using the signed proxy when it is configured."""
    if vehicle['user_id'] != user_id:
        raise HTTPException(404,'Fahrzeug nicht gefunden.')
    navigation_command_access(trip_id,user_id,vehicle['id'])
    user = db.one('SELECT * FROM users WHERE id=?',(user_id,))
    if user['provider'] == 'demo':
        data = json.loads(vehicle['data'])
        data['navigation'] = demo_navigation() | {'destination':destination}
        db.execute('UPDATE vehicles SET data=? WHERE id=?',(json.dumps(data),vehicle['id']))
        return {'accepted':True,'demo':True}
    if not settings.navigation_commands:
        raise HTTPException(503,'Tesla-Navigationsbefehle sind noch nicht aktiviert. TESLA_NAVIGATION_COMMANDS aktivieren und das Tesla-Konto mit vehicle_cmds erneut verbinden.')
    if settings.command_proxy_url and not settings.command_proxy_ready:
        raise HTTPException(503,'Die Tesla-Befehlsanbindung benötigt eine gültige HTTPS-Proxy-Adresse ohne Zugangsdaten oder URL-Pfad.')
    token = await token_for(user_id)
    navigation_command_access(trip_id,user_id,vehicle['id'])
    vin = quote(vehicle['id'].split(':')[-1],safe='')
    body = {'type':'share_ext_content_raw','value':{'android.intent.extra.TEXT':destination},'locale':'de-DE','timestamp_ms':str(int(time.time()*1000))}
    endpoint = settings.command_proxy_url or settings.fleet_url
    verify = ssl.create_default_context(cafile=settings.command_proxy_ca) if settings.command_proxy_url and settings.command_proxy_ca else True
    async with httpx.AsyncClient(timeout=25,verify=verify,follow_redirects=False) as client:
        navigation_command_access(trip_id,user_id,vehicle['id'])
        response = await client.post(endpoint+f'/api/1/vehicles/{vin}/command/navigation_request',headers={'Authorization':'Bearer '+token},json=body)
    if response.status_code != 200:
        message = {401:'Tesla-Konto erneut verbinden.',403:'Tesla-Befehlsberechtigung vehicle_cmds oder virtueller Fahrzeugschlüssel fehlt.',408:'Das Fahrzeug schläft oder ist nicht erreichbar.',429:'Tesla-Anfragelimit erreicht.'}.get(response.status_code,'Tesla hat das Navigationsziel nicht angenommen.')
        raise HTTPException(502,message)
    try:
        document = response.json()
        result = document.get('response') if isinstance(document,dict) else None
    except ValueError:
        result = None
    if not isinstance(result,dict) or result.get('result') is not True:
        raise HTTPException(502,'Tesla hat das Navigationsziel nicht bestätigt. Bitte das Auto prüfen.')
    # The received command is not proof the in-car route has been recalculated.
    data = json.loads(db.one('SELECT data FROM vehicles WHERE id=?',(vehicle['id'],))['data'])
    data['fleet_fetched_at'] = 0
    db.execute('UPDATE vehicles SET data=? WHERE id=?',(json.dumps(data),vehicle['id']))
    return {'accepted':True,'demo':False}
