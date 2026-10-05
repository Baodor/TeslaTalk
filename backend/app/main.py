import asyncio
import base64
import contextlib
import json
import logging
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo
import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from . import db, fleet, push
from .config import settings
from .metrics import ranking
from .oidc import admin_access, admin_claims, admin_denial, verification_failure
from .models import GuestLogin, Join, KeyCreate, Message, PassengerCreate, Profile, Query, Sample, TripCreate, PushSubscription, PushRemove, PushTest
from .realtime import hub, voice_token, delete_voice_room, ensure_voice_room
from .security import Identity, authenticate, current_admin, current_user, digest, driver, limiter, pin_hash, pin_matches, join_pin_hash, set_session, user_public

log = logging.getLogger('teslatalk')
oauth = OAuth()
if settings.oidc_issuer:
    oauth.register('admin', client_id=settings.oidc_client_id, client_secret=settings.oidc_client_secret,
                   server_metadata_url=settings.oidc_issuer+'/.well-known/openid-configuration',
                   client_kwargs={'scope':settings.oidc_scopes, 'code_challenge_method':'S256',
                                  'token_endpoint_auth_method':settings.oidc_token_auth_method})


def effective_end(trip):
    return min(trip['ends_at'], trip['finished_at'] or trip['ends_at'])


def access(trip_id, identity, active=False, leader=False):
    trip = db.one('SELECT * FROM trips WHERE id=?', (trip_id,))
    member = db.one('SELECT * FROM members WHERE trip_id=? AND user_id=?', (trip_id,identity.user['id']))
    if not trip or not member:
        raise HTTPException(404, 'Fahrt nicht gefunden.')
    now = time.time()
    if identity.expires_at <= now:
        raise HTTPException(401, 'Zugang abgelaufen.')
    if identity.user['provider']=='guest' and not trip['starts_at'] <= now < effective_end(trip):
        raise HTTPException(403, 'Mitfahrer-Zugang gilt nur während der Fahrt.')
    if active and (member['left_at'] is not None or not trip['starts_at'] <= now < effective_end(trip)):
        raise HTTPException(403, 'Die Fahrt ist noch nicht aktiv oder bereits beendet.')
    if leader and trip['leader_id'] != identity.user['id']:
        raise HTTPException(403, 'Nur der Fahrtleiter darf diese Aktion ausführen.')
    return trip, member


def trip_summary(trip):
    now = time.time()
    return {key:trip[key] for key in ('id','leader_id','title','destination','starts_at','ends_at','finished_at')} | {
        'status':'finished' if now>=effective_end(trip) else 'planned' if now<trip['starts_at'] else 'active',
        'participants':db.one('SELECT count(*) AS n FROM members WHERE trip_id=? AND left_at IS NULL', (trip['id'],))['n'],
    }


def participants(trip_id):
    rows = db.all_rows('SELECT u.id,u.display_name,u.username,u.plate,u.avatar_url,m.role,m.vehicle_id,m.left_at,v.name AS vehicle_name,v.model FROM members m JOIN users u ON u.id=m.user_id LEFT JOIN vehicles v ON v.id=m.vehicle_id WHERE m.trip_id=?', (trip_id,))
    for row in rows:
        row['data'] = db.one("SELECT captured_at AS updated_at,latitude,longitude,speed_kmh,heading,battery_pct,range_km,source FROM samples WHERE trip_id=? AND user_id=? AND source!='browser' ORDER BY id DESC LIMIT 1", (trip_id,row['id'])) or {}
        row['personal_location'] = db.one('SELECT updated_at,latitude,longitude,speed_kmh,heading FROM personal_locations WHERE trip_id=? AND user_id=? AND updated_at>?', (trip_id,row['id'],time.time()-300))
        row['online'] = row['id'] in hub.online()
    return rows


async def store_sample(trip_id, user_id, data):
    fields = ('latitude','longitude','speed_kmh','heading','battery_pct','range_km','odometer_km','energy_used_kwh')
    trip = db.one('SELECT * FROM trips WHERE id=?', (trip_id,))
    if not trip or not trip['starts_at'] <= time.time() < effective_end(trip):
        return
    data = dict(data)
    personal = data.get('source') == 'browser'
    if personal:
        # A person's browser position must never inherit vehicle position or metrics.
        if data.get('latitude') is None or data.get('longitude') is None:
            return
        data = {key:data.get(key) for key in ('latitude','longitude','speed_kmh','heading','source')}
    else:
        previous = db.one("SELECT * FROM samples WHERE trip_id=? AND user_id=? AND source!='browser' ORDER BY id DESC LIMIT 1", (trip_id,user_id)) or {}
        # Keep vehicle display state without carrying forward measured counters.
        for field in fields[:6]:
            if data.get(field) is None and previous.get(field) is not None:
                data[field] = previous[field]
    if not any(data.get(key) is not None for key in fields):
        return
    now = time.time()
    with db.connect() as connection:
        connection.execute('INSERT INTO samples(trip_id,user_id,captured_at,latitude,longitude,speed_kmh,heading,battery_pct,range_km,odometer_km,energy_used_kwh,source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                           (trip_id,user_id,now,*(data.get(key) for key in fields),data.get('source','telemetry')))
        if personal:
            connection.execute('INSERT INTO personal_locations VALUES (?,?,?,?,?,?,?) ON CONFLICT(trip_id,user_id) DO UPDATE SET updated_at=excluded.updated_at,latitude=excluded.latitude,longitude=excluded.longitude,speed_kmh=excluded.speed_kmh,heading=excluded.heading',
                               (trip_id,user_id,now,*(data.get(key) for key in fields[:4])))
    await hub.broadcast(trip_id, {'type':'participants','participants':participants(trip_id)})


async def background_cycle(next_poll):
    now = time.time()
    db.execute('DELETE FROM sessions WHERE expires_at<?', (now,))
    db.execute('DELETE FROM oauth_states WHERE expires_at<?', (now,))
    db.execute('DELETE FROM personal_locations WHERE updated_at<=? OR trip_id IN (SELECT id FROM trips WHERE ends_at<=? OR finished_at IS NOT NULL)', (now-300,now))
    for trip in db.all_rows('SELECT * FROM trips WHERE (ends_at<=? OR finished_at IS NOT NULL) AND voice_cleaned=0', (now,)):
        if await delete_voice_room(trip['id']):
            db.execute('UPDATE trips SET voice_cleaned=1 WHERE id=?', (trip['id'],))
        await hub.broadcast(trip['id'], {'type':'ended'})
    if now>=next_poll:
        next_poll = now+settings.poll_interval
        online = hub.online()
        members = db.all_rows('SELECT m.trip_id,m.user_id,m.vehicle_id FROM members m JOIN trips t ON t.id=m.trip_id WHERE m.left_at IS NULL AND m.vehicle_id IS NOT NULL AND t.starts_at<=? AND t.ends_at>? AND t.finished_at IS NULL', (now,now))
        cache = {}
        for member in members:
            if member['user_id'] not in online:
                continue
            try:
                vehicle = db.one('SELECT * FROM vehicles WHERE id=? AND user_id=?', (member['vehicle_id'],member['user_id']))
                if not vehicle:
                    continue
                if vehicle['id'] not in cache:
                    cache[vehicle['id']] = await fleet.fetch_vehicle(member['user_id'], vehicle)
                await store_sample(member['trip_id'], member['user_id'], cache[vehicle['id']])
            except (HTTPException,httpx.HTTPError,ValueError) as error:
                log.info('Fleet retrieval unavailable: %s', type(error).__name__)
    return next_poll


async def background():
    next_poll = 0
    while True:
        try:
            next_poll = await background_cycle(next_poll)
        except Exception as error:
            # Keep expiry cleanup, room shutdown and polling alive after a
            # temporary failure. Do not log provider responses or credentials.
            log.warning('Background maintenance unavailable: %s', type(error).__name__)
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app):
    if len(settings.secret)<32:
        raise RuntimeError('APP_SECRET benötigt mindestens 32 Zeichen. Bitte scripts/configure.py ausführen.')
    if settings.secure and not settings.livekit_url.startswith('wss://'):
        raise RuntimeError('LIVEKIT_URL muss bei HTTPS mit wss:// beginnen.')
    ZoneInfo(settings.timezone)
    db.initialize()
    tasks = [asyncio.create_task(background()), asyncio.create_task(push.worker())]
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title='TeslaTalk API', version='0.1.0', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret, session_cookie='tt_oidc', https_only=settings.secure, same_site='lax')


@app.middleware('http')
async def security_headers(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS') and not request.headers.get('authorization'):
        if request.headers.get('origin') != settings.app_url:
            return JSONResponse({'detail':'Ungültiger Ursprung der Anfrage.'}, status_code=403)
    try:
        too_large = int(request.headers.get('content-length','0') or 0)>1_048_576
    except ValueError:
        return JSONResponse({'detail':'Ungültige Anfragegröße.'}, status_code=400)
    if too_large:
        return JSONResponse({'detail':'Anfrage zu groß.'}, status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Permissions-Policy']='camera=(), microphone=(self), geolocation=(self)'
    response.headers['Cache-Control']='no-store' if request.url.path.startswith(('/api','/auth','/guest','/share')) else 'no-cache'
    media_origin = urlparse(settings.livekit_url)
    lk = f'{media_origin.scheme}://{media_origin.netloc}'
    lk_http = lk.replace('wss://','https://').replace('ws://','http://')
    response.headers['Content-Security-Policy']=f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; connect-src 'self' {lk} {lk_http}; media-src 'self' blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(request, error):
    return JSONResponse({'detail':'Dieser Name, dieses Kennzeichen oder dieser Eintrag existiert bereits.'}, status_code=409)


@app.exception_handler(httpx.HTTPError)
async def upstream_error(request, error):
    return JSONResponse({'detail':'Externer Dienst derzeit nicht erreichbar.'}, status_code=502)


@app.get('/api/health')
def health():
    db.one('SELECT 1')
    return {'status':'ok','version':'0.1.0'}


@app.get('/api/config')
def config():
    return {'version':'0.1.0','demo':settings.demo,'tesla_ready':settings.tesla_ready,'voice_ready':settings.voice_ready,
            'admin_ready':bool(settings.oidc_issuer and settings.oidc_client_id), 'app_url':settings.app_url,
            'push_ready':settings.push_ready,'vapid_public_key':settings.vapid_public_key if settings.push_ready else ''}


@app.post('/api/push/subscribe')
def push_subscribe(body:PushSubscription, request:Request, identity:Identity=Depends(current_user)):
    limiter.check(('push',identity.user['id']),15,60)
    if request.headers.get('authorization'):
        raise HTTPException(403,'Push-Abonnements benötigen eine Browser-Anmeldung.')
    push.subscribe(body.model_dump(),identity,request.cookies.get('tt_session',''))
    return {'ok':True,'expires_at':identity.expires_at}


@app.post('/api/push/unsubscribe')
def push_unsubscribe(body:PushRemove,identity:Identity=Depends(current_user)):
    db.execute('DELETE FROM push_subscriptions WHERE endpoint_hash=? AND user_id=?',(digest(body.endpoint),identity.user['id']))
    return {'ok':True}


@app.post('/api/push/test')
async def push_test(body:PushTest,request:Request,identity:Identity=Depends(current_user)):
    if request.headers.get('authorization'):
        raise HTTPException(403,'Push-Test benötigt eine Browser-Anmeldung.')
    if identity.user['provider']=='guest':
        member=db.one('SELECT trip_id FROM members WHERE user_id=?',(identity.user['id'],))
        if not member:
            raise HTTPException(403,'Mitfahrer-Zugang ist nicht mehr gültig.')
        access(member['trip_id'],identity,active=True)
    limiter.check(('push-test',identity.user['id']),3,60)
    if body.keys is not None:
        push.subscribe(body.model_dump(exclude_none=True),identity,request.cookies.get('tt_session',''))
    timing=await push.test_message(body.endpoint,identity,request.cookies.get('tt_session',''))
    return {'ok':True,'accepted_by_provider':True,**timing}


@app.get('/auth/tesla')
def tesla_login():
    if not settings.tesla_ready:
        raise HTTPException(503, 'Tesla-Anmeldung ist noch nicht konfiguriert.')
    state, binding, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    db.execute('INSERT INTO oauth_states VALUES (?,?,?,?)', (digest(state),digest(binding),verifier,time.time()+600))
    challenge = base64.urlsafe_b64encode(__import__('hashlib').sha256(verifier.encode()).digest()).decode().rstrip('=')
    parameters = {'client_id':settings.tesla_client_id,'response_type':'code','redirect_uri':settings.app_url+'/auth/tesla/callback',
                  'scope':'openid offline_access user_data vehicle_device_data vehicle_location','state':state,'nonce':secrets.token_urlsafe(24),
                  'code_challenge':challenge,'code_challenge_method':'S256','locale':'de-DE','require_requested_scopes':'true'}
    response = RedirectResponse('https://auth.tesla.com/oauth2/v3/authorize?'+urlencode(parameters))
    response.set_cookie('tt_oauth',binding,max_age=600,httponly=True,secure=settings.secure,samesite='lax')
    return response


@app.get('/auth/tesla/callback')
async def tesla_callback(request:Request, state:str='', code:str=''):
    with db.connect() as connection:
        pending = connection.execute('SELECT * FROM oauth_states WHERE state_hash=?', (digest(state),)).fetchone()
        if not pending or pending['expires_at']<time.time() or pending['binding_hash']!=digest(request.cookies.get('tt_oauth','')):
            raise HTTPException(400, 'Anmeldung abgelaufen oder ungültig. Bitte neu starten.')
        connection.execute('DELETE FROM oauth_states WHERE state_hash=?', (digest(state),))
    if not code:
        return RedirectResponse('/?error=tesla_cancelled')
    async with httpx.AsyncClient(timeout=25) as client:
        result = await client.post(fleet.TOKEN_URL, data={'grant_type':'authorization_code','client_id':settings.tesla_client_id,
                                    'client_secret':settings.tesla_client_secret,'code':code,'code_verifier':pending['verifier'],
                                    'audience':settings.fleet_url,'redirect_uri':settings.app_url+'/auth/tesla/callback'})
        if result.status_code!=200:
            raise HTTPException(502, 'Tesla-Anmeldung fehlgeschlagen. Bitte erneut versuchen.')
        token = result.json()
        account = await client.get(settings.fleet_url+'/api/1/users/me',headers={'Authorization':'Bearer '+token['access_token']})
        if account.status_code!=200:
            raise HTTPException(502, 'Tesla-Konto konnte nicht gelesen werden.')
        profile = account.json().get('response') or {}
    if not profile.get('email') and not profile.get('id'):
        raise HTTPException(502, 'Tesla lieferte keine eindeutige Kontoidentität.')
    subject = str(profile.get('id') or profile['email'].lower())
    user = db.one('SELECT * FROM users WHERE subject=?', ('tesla:'+subject,))
    if not user:
        uid = str(uuid.uuid4())
        db.execute('INSERT INTO users(id,provider,subject,username,display_name,email,created_at) VALUES (?,?,?,?,?,?,?)',
                   (uid,'tesla','tesla:'+subject,'fahrer-'+uid[:8],profile.get('full_name') or 'Tesla-Fahrer',profile.get('email'),time.time()))
    else:
        uid=user['id']
    db.execute('UPDATE users SET avatar_url=? WHERE id=?', (fleet.profile_avatar(profile),uid))
    fleet.save_token(uid,token)
    response=RedirectResponse('/',status_code=303)
    response.delete_cookie('tt_oauth')
    set_session(response,uid)
    return response


@app.get('/auth/admin')
async def admin_login(request:Request):
    if not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(503, 'OIDC-Administration ist noch nicht konfiguriert.')
    try:
        return await oauth.admin.authorize_redirect(request, settings.app_url+'/auth/admin/callback')
    except Exception as error:
        message, diagnostic = verification_failure(error, 'authorization_redirect')
        log.warning('OIDC verification failed: %s', json.dumps(diagnostic, sort_keys=True))
        raise HTTPException(400, message) from None


@app.get('/auth/admin/callback')
async def admin_callback(request:Request):
    stage = 'token_exchange_and_validation'
    try:
        token=await oauth.admin.authorize_access_token(request)
        stage = 'identity_claims'
        claims=await admin_claims(oauth.admin, token)
        allowed, diagnostic=admin_access(claims)
        if not allowed:
            log.warning('OIDC admin access denied: %s', json.dumps(diagnostic, sort_keys=True))
            raise HTTPException(403, admin_denial(diagnostic))
        response=RedirectResponse('/admin',status_code=303)
        set_session(response,str(claims['sub']),expires_at=time.time()+8*3600,admin=True)
        request.session.clear()
        return response
    except HTTPException:
        raise
    except Exception as error:
        message, diagnostic = verification_failure(error, stage)
        log.warning('OIDC verification failed: %s', json.dumps(diagnostic, sort_keys=True))
        request.session.clear()
        raise HTTPException(400, message) from None


@app.post('/auth/logout')
def logout(request:Request):
    for cookie in ('tt_session','tt_admin'):
        db.execute('DELETE FROM sessions WHERE token_hash=?', (digest(request.cookies.get(cookie,'')),))
    response=JSONResponse({'ok':True})
    response.delete_cookie('tt_session')
    response.delete_cookie('tt_admin')
    request.session.clear()
    return response


@app.post('/api/demo/login')
def demo_login(request:Request, body:Query):
    if not settings.demo:
        raise HTTPException(404,'Nicht gefunden.')
    limiter.check(('demo',request.client.host),10)
    name=body.query.strip()
    user=db.one('SELECT * FROM users WHERE subject=?', ('demo:'+name.casefold(),))
    if not user:
        uid=str(uuid.uuid4())
        db.execute('INSERT INTO users(id,provider,subject,username,display_name,created_at) VALUES (?,?,?,?,?,?)',
                   (uid,'demo','demo:'+name.casefold(),'demo-'+uid[:8],name,time.time()))
        vehicle_id='demo-'+uid
        data={'battery_pct':78,'range_km':386,'latitude':49.8728,'longitude':8.6512,'speed_kmh':0,'heading':90,'source':'demo','updated_at':time.time()}
        db.execute('INSERT INTO vehicles VALUES (?,?,?,?,?)', (vehicle_id,uid,'Demo Model 3','Model 3',json.dumps(data)))
        db.execute('UPDATE users SET favorite_vehicle=? WHERE id=?', (vehicle_id,uid))
    else:
        uid=user['id']
    response=JSONResponse({'ok':True})
    set_session(response,uid)
    return response


@app.get('/api/me')
def me(identity:Identity=Depends(current_user)):
    return user_public(identity.user)


@app.patch('/api/me')
def profile(body:Profile, identity:Identity=Depends(current_user)):
    driver(identity)
    db.execute('UPDATE users SET username=?,display_name=?,plate=? WHERE id=?',
               (body.username.strip(),body.display_name.strip(),''.join(body.plate.upper().split()) or None,identity.user['id']))
    return user_public(db.one('SELECT * FROM users WHERE id=?',(identity.user['id'],)))


@app.post('/api/me/tesla-profile')
async def refresh_tesla_profile(identity:Identity=Depends(current_user)):
    driver(identity)
    if identity.user['provider'] != 'tesla':
        raise HTTPException(409, 'Profilbilder werden über dein verbundenes Tesla-Konto geladen.')
    limiter.check(('tesla-profile',identity.user['id']),3,60)
    profile = await fleet.request(identity.user['id'], '/api/1/users/me')
    if not isinstance(profile, dict):
        raise HTTPException(502, 'Tesla lieferte kein nutzbares Kontoprofil.')
    db.execute('UPDATE users SET avatar_url=? WHERE id=?', (fleet.profile_avatar(profile),identity.user['id']))
    return user_public(db.one('SELECT * FROM users WHERE id=?',(identity.user['id'],)))


@app.get('/api/vehicles')
def vehicles(identity:Identity=Depends(current_user)):
    driver(identity)
    rows=db.all_rows('SELECT * FROM vehicles WHERE user_id=?',(identity.user['id'],))
    return [row | {'data':json.loads(row['data'])} for row in rows]


@app.post('/api/vehicles/sync')
async def sync_vehicles(identity:Identity=Depends(current_user)):
    driver(identity)
    limiter.check(('sync',identity.user['id']),3,60)
    await fleet.synchronize(identity.user['id'])
    return vehicles(identity)


@app.post('/api/vehicles/{vehicle_id}/select')
def select_vehicle(vehicle_id:str, identity:Identity=Depends(current_user)):
    driver(identity)
    if not db.one('SELECT id FROM vehicles WHERE id=? AND user_id=?',(vehicle_id,identity.user['id'])):
        raise HTTPException(404,'Fahrzeug nicht gefunden.')
    db.execute('UPDATE users SET favorite_vehicle=? WHERE id=?',(vehicle_id,identity.user['id']))
    db.execute('UPDATE members SET vehicle_id=? WHERE user_id=? AND left_at IS NULL AND trip_id IN (SELECT id FROM trips WHERE ends_at>? AND finished_at IS NULL)',(vehicle_id,identity.user['id'],time.time()))
    return {'ok':True}


@app.post('/api/vehicles/{vehicle_id}/refresh')
async def refresh_vehicle(vehicle_id:str,identity:Identity=Depends(current_user)):
    driver(identity)
    limiter.check(('refresh',identity.user['id']),5,60)
    vehicle=db.one('SELECT * FROM vehicles WHERE id=? AND user_id=?',(vehicle_id,identity.user['id']))
    if not vehicle:
        raise HTTPException(404,'Fahrzeug nicht gefunden.')
    data=await fleet.fetch_vehicle(identity.user['id'],vehicle)
    for member in db.all_rows('SELECT t.id FROM trips t JOIN members m ON t.id=m.trip_id WHERE m.user_id=? AND m.left_at IS NULL AND t.starts_at<=? AND t.ends_at>? AND t.finished_at IS NULL',(identity.user['id'],time.time(),time.time())):
        await store_sample(member['id'],identity.user['id'],data)
    return data


def lookup(query):
    user=db.one("SELECT * FROM users WHERE provider!='guest' AND (username=? COLLATE NOCASE OR plate=? OR email=? COLLATE NOCASE)",
                (query.strip(),''.join(query.upper().split()),query.strip()))
    if not user:
        raise HTTPException(404,'Kein passendes Fahrer-Konto gefunden.')
    return user


@app.get('/api/friends')
def friends(identity:Identity=Depends(current_user)):
    driver(identity)
    uid=identity.user['id']
    rows=db.all_rows('SELECT * FROM friendships WHERE low_id=? OR high_id=?',(uid,uid))
    return [row | {'user':user_public(db.one('SELECT * FROM users WHERE id=?',(row['high_id'] if row['low_id']==uid else row['low_id'],))), 'incoming':row['requester']!=uid} for row in rows]


@app.post('/api/friends')
def request_friend(body:Query, identity:Identity=Depends(current_user)):
    driver(identity)
    limiter.check(('friend',identity.user['id']),10,60)
    other=lookup(body.query)
    uid=identity.user['id']
    if uid==other['id']:
        raise HTTPException(400,'Das ist dein eigenes Konto.')
    low,high=sorted([uid,other['id']])
    db.execute('INSERT INTO friendships VALUES (?,?,?,?,?)',(low,high,uid,'pending',time.time()))
    push.enqueue(other['id'],identity.user['display_name']+' möchte sich mit dir verbinden.','/', 'friend-'+uid)
    return {'ok':True}


@app.post('/api/friends/{other_id}/accept')
def accept_friend(other_id:str, identity:Identity=Depends(current_user)):
    driver(identity)
    low,high=sorted([identity.user['id'],other_id])
    if not db.execute("UPDATE friendships SET status='accepted' WHERE low_id=? AND high_id=? AND requester!=?",(low,high,identity.user['id'])):
        raise HTTPException(404,'Anfrage nicht gefunden.')
    return {'ok':True}


@app.delete('/api/friends/{other_id}')
def delete_friend(other_id:str,identity:Identity=Depends(current_user)):
    driver(identity)
    low,high=sorted([identity.user['id'],other_id])
    db.execute('DELETE FROM friendships WHERE low_id=? AND high_id=?',(low,high))
    return {'ok':True}


@app.get('/api/trips')
def trips(identity:Identity=Depends(current_user)):
    rows=db.all_rows('SELECT t.* FROM trips t JOIN members m ON m.trip_id=t.id WHERE m.user_id=? ORDER BY t.starts_at DESC LIMIT 200',(identity.user['id'],))
    if identity.user['provider']=='guest':
        rows=[row for row in rows if row['starts_at']<=time.time()<effective_end(row)]
    return [trip_summary(row) for row in rows]


@app.post('/api/trips')
def create_trip(body:TripCreate,identity:Identity=Depends(current_user)):
    driver(identity)
    limiter.check(('trip',identity.user['id']),5,60)
    if body.ends_at.timestamp()<=time.time():
        raise HTTPException(400,'Fahrtende muss in der Zukunft liegen.')
    uid=identity.user['id']
    if not identity.user['favorite_vehicle']:
        raise HTTPException(409,'Bitte zuerst dein Tesla-Fahrzeug auswählen.')
    trip_id=str(uuid.uuid4())
    pin=f'{secrets.randbelow(1_000_000):06d}'
    while db.one('SELECT id FROM trips WHERE pin_hash=?', (join_pin_hash(pin),)):
        pin=f'{secrets.randbelow(1_000_000):06d}'
    with db.connect() as connection:
        connection.execute('INSERT INTO trips(id,leader_id,title,destination,starts_at,ends_at,pin_hash,guest_key,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                           (trip_id,uid,body.title.strip(),body.destination.strip(),body.starts_at.timestamp(),body.ends_at.timestamp(),join_pin_hash(pin),secrets.token_urlsafe(32),time.time()))
        connection.execute('INSERT INTO members VALUES (?,?,?,?,?,NULL)',(trip_id,uid,'driver',identity.user['favorite_vehicle'],time.time()))
    return trip_summary(db.one('SELECT * FROM trips WHERE id=?',(trip_id,))) | {'pin':pin}


@app.post('/api/trips/join')
def join_trip(request:Request,body:Join,identity:Identity=Depends(current_user)):
    driver(identity)
    limiter.check(('join',identity.user['id']),5,300)
    if not identity.user['favorite_vehicle']:
        raise HTTPException(409,'Bitte zuerst dein Fahrzeug auswählen.')
    found=db.one('SELECT * FROM trips WHERE pin_hash=? AND ends_at>? AND finished_at IS NULL', (join_pin_hash(body.pin),time.time()))
    if not found:
        raise HTTPException(404,'PIN ungültig oder Fahrt beendet.')
    db.execute('INSERT INTO members VALUES (?,?,?,?,?,NULL) ON CONFLICT(trip_id,user_id) DO UPDATE SET left_at=NULL,vehicle_id=excluded.vehicle_id',
               (found['id'],identity.user['id'],'driver',identity.user['favorite_vehicle'],time.time()))
    return trip_summary(found)


@app.get('/api/invites')
def invitations(identity:Identity=Depends(current_user)):
    return [trip_summary(row) for row in db.all_rows('SELECT t.* FROM trips t JOIN invites i ON i.trip_id=t.id WHERE i.user_id=? AND t.ends_at>? AND t.finished_at IS NULL',(identity.user['id'],time.time()))]


@app.post('/api/trips/{trip_id}/invite')
def invite(trip_id:str,body:Query,identity:Identity=Depends(current_user)):
    trip,_=access(trip_id,identity,leader=True)
    driver(identity)
    limiter.check(('invite',identity.user['id']),20,60)
    if effective_end(trip)<=time.time():
        raise HTTPException(403,'Die Fahrt ist bereits beendet.')
    other=lookup(body.query)
    inserted=db.execute('INSERT INTO invites VALUES (?,?,?) ON CONFLICT DO NOTHING',(trip_id,other['id'],time.time()))
    if inserted:
        push.enqueue(other['id'],'Du bist zur Fahrt „'+trip['title']+'“ eingeladen.','/','invite-'+trip_id)
    return {'ok':True,'user':user_public(other)}


@app.post('/api/trips/{trip_id}/accept')
def accept_invite(trip_id:str,identity:Identity=Depends(current_user)):
    driver(identity)
    trip=db.one('SELECT * FROM trips WHERE id=?',(trip_id,))
    if not trip or effective_end(trip)<=time.time() or not db.one('SELECT * FROM invites WHERE trip_id=? AND user_id=?',(trip_id,identity.user['id'])):
        raise HTTPException(404,'Einladung ungültig oder abgelaufen.')
    if not identity.user['favorite_vehicle']:
        raise HTTPException(409,'Bitte zuerst dein Fahrzeug auswählen.')
    with db.connect() as connection:
        connection.execute('INSERT INTO members VALUES (?,?,?,?,?,NULL) ON CONFLICT(trip_id,user_id) DO UPDATE SET left_at=NULL',(trip_id,identity.user['id'],'driver',identity.user['favorite_vehicle'],time.time()))
        connection.execute('DELETE FROM invites WHERE trip_id=? AND user_id=?',(trip_id,identity.user['id']))
    return trip_summary(trip)


@app.get('/api/trips/{trip_id}')
def trip_detail(trip_id:str,identity:Identity=Depends(current_user)):
    trip,member=access(trip_id,identity)
    result=trip_summary(trip) | {'participants_detail':participants(trip_id),'my_role':member['role'],
        'album':{'status':'planned','name':album_name(trip),'url':None}}
    if trip['leader_id']==identity.user['id']:
        result['guest_url']=settings.app_url+'/guest/'+trip['guest_key']
        result['share_url']=settings.app_url+'/share/'+trip['public_key'] if trip['public_key'] else None
        result['passengers']=db.all_rows('SELECT id,name,user_id FROM passengers WHERE trip_id=?',(trip_id,))
    return result


def album_name(trip):
    zone=ZoneInfo(settings.timezone)
    start=datetime.fromtimestamp(trip['starts_at'],zone).strftime('%Y-%m-%d')
    end=datetime.fromtimestamp(trip['ends_at'],zone).strftime('%Y-%m-%d')
    return trip['title']+' · '+start+' – '+end


@app.post('/api/trips/{trip_id}/passengers')
def add_passenger(trip_id:str,body:PassengerCreate,identity:Identity=Depends(current_user)):
    trip,_=access(trip_id,identity,leader=True)
    if effective_end(trip)<=time.time():
        raise HTTPException(403,'Fahrt bereits beendet.')
    pid=str(uuid.uuid4())
    pin=f'{secrets.randbelow(1_000_000):06d}'
    db.execute('INSERT INTO passengers VALUES (?,?,?,?,?,NULL)',(pid,trip_id,body.name.strip(),body.name.strip().casefold(),pin_hash(pin)))
    return {'id':pid,'name':body.name.strip(),'pin':pin}


@app.get('/api/guest/{key}')
def guest_info(key:str):
    trip=db.one('SELECT * FROM trips WHERE guest_key=?',(key,))
    if not trip:
        raise HTTPException(404,'Mitfahrer-Link nicht gefunden.')
    return {'title':trip['title'],'starts_at':trip['starts_at'],'ends_at':effective_end(trip),
            'active':trip['starts_at']<=time.time()<effective_end(trip)}


@app.post('/api/guest/{key}/login')
def guest_login(key:str,body:GuestLogin,request:Request):
    limiter.check(('guest',request.client.host,key),5,300)
    trip=db.one('SELECT * FROM trips WHERE guest_key=?',(key,))
    if not trip or not trip['starts_at']<=time.time()<effective_end(trip):
        raise HTTPException(403,'Mitfahrer-Zugang ist außerhalb des Fahrtzeitraums gesperrt.')
    passenger=db.one('SELECT * FROM passengers WHERE trip_id=? AND normalized_name=?',(trip['id'],body.name.strip().casefold()))
    if not passenger or not pin_matches(body.pin,passenger['pin_hash']):
        raise HTTPException(401,'Name oder PIN ungültig.')
    with db.connect() as connection:
        current=connection.execute('SELECT * FROM passengers WHERE id=?',(passenger['id'],)).fetchone()
        uid=current['user_id']
        if not uid:
            uid=str(uuid.uuid4())
            connection.execute('INSERT INTO users(id,provider,subject,username,display_name,created_at) VALUES (?,?,?,?,?,?)',
                               (uid,'guest','guest:'+passenger['id'],'gast-'+uid[:8],passenger['name'],time.time()))
            connection.execute('UPDATE passengers SET user_id=? WHERE id=?',(uid,passenger['id']))
            connection.execute('INSERT INTO members VALUES (?,?,?,NULL,?,NULL)',(trip['id'],uid,'passenger',time.time()))
    response=JSONResponse({'trip_id':trip['id']})
    set_session(response,uid,expires_at=effective_end(trip))
    return response


@app.get('/api/trips/{trip_id}/messages')
def messages(trip_id:str,before:float|None=None,identity:Identity=Depends(current_user)):
    access(trip_id,identity)
    rows=db.all_rows('SELECT m.*,u.display_name FROM messages m JOIN users u ON u.id=m.user_id WHERE m.trip_id=? AND m.created_at<? ORDER BY m.created_at DESC LIMIT 100',(trip_id,before or time.time()+1))
    return list(reversed(rows))


@app.post('/api/trips/{trip_id}/messages')
async def post_message(trip_id:str,body:Message,identity:Identity=Depends(current_user)):
    trip,member=access(trip_id,identity)
    if effective_end(trip)<=time.time() or member['left_at'] is not None:
        raise HTTPException(403,'Chat ist nach Fahrtende nur lesbar.')
    limiter.check(('chat',identity.user['id']),30,60)
    message={'id':str(uuid.uuid4()),'trip_id':trip_id,'user_id':identity.user['id'],'text':body.text,
             'created_at':time.time(),'display_name':identity.user['display_name']}
    db.execute('INSERT INTO messages VALUES (?,?,?,?,?)',tuple(message[key] for key in ('id','trip_id','user_id','text','created_at')))
    for row in db.all_rows('SELECT user_id FROM members WHERE trip_id=? AND user_id!=? AND left_at IS NULL',(trip_id,identity.user['id'])):
        push.enqueue(row['user_id'],identity.user['display_name']+': neue Nachricht in „'+trip['title']+'“.','/trip/'+trip_id,'chat-'+trip_id,trip_id)
    await hub.broadcast(trip_id,{'type':'message','message':message})
    return message


@app.post('/api/trips/{trip_id}/samples')
async def upload_sample(trip_id:str,body:Sample,request:Request,identity:Identity=Depends(current_user)):
    access(trip_id,identity,active=True)
    limiter.check(('sample',identity.user['id']),15,60)
    data=body.model_dump()
    if body.source=='browser':
        if body.latitude is None:
            raise HTTPException(422,'Der persönliche Standort benötigt Breite und Länge.')
        data={key:data[key] for key in ('latitude','longitude','speed_kmh','heading','source')}
    else:
        driver(identity)
        if not request.headers.get('authorization'):
            raise HTTPException(403,'Telemetrie-Import benötigt einen persönlichen API-Schlüssel.')
    await store_sample(trip_id,identity.user['id'],data)
    return {'ok':True}


@app.delete('/api/trips/{trip_id}/location')
async def stop_location(trip_id:str,identity:Identity=Depends(current_user)):
    access(trip_id,identity)
    db.execute('DELETE FROM personal_locations WHERE trip_id=? AND user_id=?',(trip_id,identity.user['id']))
    await hub.broadcast(trip_id,{'type':'participants','participants':participants(trip_id)})
    return {'ok':True}


@app.get('/api/trips/{trip_id}/history')
def history(trip_id:str,after_id:int=0,limit:int=1000,identity:Identity=Depends(current_user)):
    access(trip_id,identity)
    return db.all_rows('SELECT * FROM samples WHERE trip_id=? AND id>? ORDER BY id LIMIT ?',(trip_id,after_id,max(1,min(limit,5000))))


@app.get('/api/trips/{trip_id}/export')
def export_history(trip_id:str,identity:Identity=Depends(current_user)):
    access(trip_id,identity)
    def stream():
        yield '['
        last=0
        first=True
        while True:
            rows=db.all_rows('SELECT * FROM samples WHERE trip_id=? AND id>? ORDER BY id LIMIT 1000',(trip_id,last))
            if not rows:
                break
            for row in rows:
                yield ('' if first else ',')+json.dumps(row)
                first=False
            last=rows[-1]['id']
        yield ']'
    return StreamingResponse(stream(),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="teslatalk-{trip_id}.json"'})


@app.get('/api/trips/{trip_id}/ranking')
def trip_ranking(trip_id:str,identity:Identity=Depends(current_user)):
    access(trip_id,identity)
    return ranking(db.all_rows("SELECT * FROM samples WHERE trip_id=? AND source!='browser' ORDER BY captured_at",(trip_id,)))


@app.post('/api/trips/{trip_id}/voice-token')
async def voice_access(trip_id:str,identity:Identity=Depends(current_user)):
    trip,_=access(trip_id,identity,active=True)
    if not settings.voice_ready:
        raise HTTPException(503,'Sprachfunk ist noch nicht konfiguriert.')
    if not await ensure_voice_room(trip_id):
        raise HTTPException(503,'Audioserver derzeit nicht erreichbar.')
    return {'token':voice_token(trip_id,identity,min(identity.expires_at,effective_end(trip))),
            'url':settings.livekit_url,'ends_at':effective_end(trip)}


@app.post('/api/trips/{trip_id}/finish')
async def finish_trip(trip_id:str,identity:Identity=Depends(current_user)):
    access(trip_id,identity,leader=True)
    db.execute('UPDATE trips SET finished_at=? WHERE id=? AND finished_at IS NULL',(time.time(),trip_id))
    db.execute('DELETE FROM personal_locations WHERE trip_id=?',(trip_id,))
    await hub.broadcast(trip_id,{'type':'ended'})
    if await delete_voice_room(trip_id):
        db.execute('UPDATE trips SET voice_cleaned=1 WHERE id=?',(trip_id,))
    return {'ok':True}


@app.post('/api/trips/{trip_id}/share')
def share_trip(trip_id:str,identity:Identity=Depends(current_user)):
    trip,_=access(trip_id,identity,leader=True)
    if effective_end(trip)>time.time():
        raise HTTPException(403,'Öffentlicher Leselink ist erst nach Fahrtende verfügbar.')
    key=secrets.token_urlsafe(32)
    db.execute('UPDATE trips SET public_key=? WHERE id=?',(key,trip_id))
    return {'url':settings.app_url+'/share/'+key}


@app.delete('/api/trips/{trip_id}/share')
def revoke_share(trip_id:str,identity:Identity=Depends(current_user)):
    access(trip_id,identity,leader=True)
    db.execute('UPDATE trips SET public_key=NULL WHERE id=?',(trip_id,))
    return {'ok':True}


@app.get('/api/public/{key}')
def public_trip(key:str):
    trip=db.one('SELECT * FROM trips WHERE public_key=?',(key,))
    if not trip or time.time()<effective_end(trip):
        raise HTTPException(404,'Freigabe nicht gefunden.')
    # Public links never expose private chat, precise GPS history, plates or Tesla identities.
    return {key:trip[key] for key in ('title','destination','starts_at','ends_at')} | {'album':{'status':'planned','name':album_name(trip),'url':None},'read_only':True}


@app.get('/api/keys')
def keys(identity:Identity=Depends(current_user)):
    driver(identity)
    rows=db.all_rows('SELECT id,label,expires_at,created_at FROM api_keys WHERE user_id=?',(identity.user['id'],))
    return [row | {'expires_at':row['expires_at'] or None} for row in rows]


@app.post('/api/keys')
def create_key(body:KeyCreate,identity:Identity=Depends(current_user)):
    driver(identity)
    limiter.check(('key',identity.user['id']),5,60)
    token='tt_'+secrets.token_urlsafe(32)
    key_id=str(uuid.uuid4())
    expiry=time.time()+body.days*86400 if body.days is not None else 0
    db.execute('INSERT INTO api_keys VALUES (?,?,?,?,?,?)',(key_id,identity.user['id'],digest(token),body.label,expiry,time.time()))
    return {'id':key_id,'token':token,'expires_at':expiry or None}


@app.delete('/api/keys/{key_id}')
def delete_key(key_id:str,identity:Identity=Depends(current_user)):
    driver(identity)
    db.execute('DELETE FROM api_keys WHERE id=? AND user_id=?',(key_id,identity.user['id']))
    return {'ok':True}


@app.get('/api/admin')
def admin(identity:Identity=Depends(current_admin)):
    return {'version':'0.1.0','users':db.one('SELECT count(*) n FROM users')['n'],
            'trips':db.one('SELECT count(*) n FROM trips')['n'],'samples':db.one('SELECT count(*) n FROM samples')['n'],
            'online':len(hub.online()),'tesla_ready':settings.tesla_ready,'voice_ready':settings.voice_ready,
            'poll_interval':settings.poll_interval,'demo':settings.demo,'push_ready':settings.push_ready,
            'storage':'SQLite / persistentes Volume'}


@app.post('/api/admin/push/test')
def admin_push_test(identity:Identity=Depends(current_admin)):
    limiter.check(('admin-push-test',),3,60)
    return push.test_all_devices()


@app.get('/api/openapi.json')
def openapi(identity:Identity=Depends(current_user)):
    return app.openapi()


@app.websocket('/api/ws/trips/{trip_id}')
async def trip_socket(socket:WebSocket,trip_id:str):
    try:
        if socket.headers.get('origin') != settings.app_url and not socket.headers.get('authorization'):
            await socket.close(code=1008)
            return
        identity=authenticate(socket.headers,socket.cookies)
        access(trip_id,identity)
    except HTTPException:
        await socket.close(code=1008)
        return
    await socket.accept()
    hub.add(trip_id,socket,identity.user['id'])
    try:
        await socket.send_json({'type':'participants','participants':participants(trip_id)})
        while True:
            identity=authenticate(socket.headers,socket.cookies)
            access(trip_id,identity)
            try:
                message=await asyncio.wait_for(socket.receive_text(),timeout=5)
                if len(message)>1024:
                    await socket.close(code=1009)
                    break
            except asyncio.TimeoutError:
                await socket.send_json({'type':'heartbeat'})
    except (WebSocketDisconnect,HTTPException,RuntimeError):
        with contextlib.suppress(Exception):
            await socket.close(code=1008)
    finally:
        hub.remove(trip_id,socket)


assets=Path(settings.frontend_dir)/'assets'
if assets.exists():
    app.mount('/assets',StaticFiles(directory=assets),name='assets')


@app.get('/.well-known/appspecific/com.tesla.3p.public-key.pem')
def tesla_public_key():
    path=Path(settings.public_key_path)
    if not path.is_file():
        raise HTTPException(404,'Tesla-Public-Key noch nicht hinterlegt.')
    return FileResponse(path,media_type='application/x-pem-file')


@app.get('/apple-touch-icon.png')
@app.get('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    path=Path(settings.frontend_dir)/'apple-touch-icon-v4.png'
    if not path.is_file():
        raise HTTPException(404, 'App-Icon noch nicht gebaut.')
    return FileResponse(path, media_type='image/png')


@app.get('/{path:path}')
def frontend(path:str):
    if path.startswith(('api/','auth/')):
        raise HTTPException(404,'Nicht gefunden.')
    root=Path(settings.frontend_dir)
    requested=(root/path).resolve()
    if root.resolve() in requested.parents and requested.is_file():
        return FileResponse(requested)
    if (root/'index.html').is_file():
        return FileResponse(root/'index.html')
    raise HTTPException(503,'Frontend noch nicht gebaut.')
