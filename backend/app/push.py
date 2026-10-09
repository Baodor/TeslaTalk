"""Opt-in Web Push, encrypted subscriptions and a bounded persistent outbox."""
import asyncio
import base64
import json
import logging
import re
import secrets
import time
from urllib.parse import urlsplit
from fastapi import HTTPException
from pywebpush import webpush, WebPushException
import requests
from . import db
from .config import settings
from .security import cipher, digest

MAX_DELIVERIES = 4
log = logging.getLogger('teslatalk.push')


def localize_payload(payload, language):
    """Translate application notification templates, preserving names and trip titles."""
    data = json.loads(payload)
    if language not in ('en','nl','de-AT'):
        if 'message_key' not in data:
            return payload
        data.pop('message_key',None)
        data.pop('parameters',None)
        return json.dumps(data,ensure_ascii=False)
    titles = {
        'TeslaTalk · Testnachricht': ('TeslaTalk · Test notification','TeslaTalk · Testmelding','TeslaTalk · Servas, des is a Test'),
        'TeslaTalk · Server-Testnachricht': ('TeslaTalk · Server test notification','TeslaTalk · Servertestmelding','TeslaTalk · Da Server probiert was'),
    }
    bodies = {
        'Deine Benachrichtigungen erreichen dieses Gerät.': ('Your notifications reach this device.','Je meldingen bereiken dit apparaat.','Deine Benachrichtigungen kumman auf dem Gerät an.'),
        'Deine TeslaTalk-Administration testet die Benachrichtigungen.': ('Your TeslaTalk administrator is testing notifications.','Je TeslaTalk-beheerder test de meldingen.','Dei TeslaTalk-Verwaltung probiert de Benachrichtigungen aus.'),
        'Eine übernommene Fahrzeugroute weicht ab oder kann nicht gefahren werden. Bitte Routenübersicht prüfen.': ('An accepted vehicle route differs or cannot be driven. Please check the route overview.','Een overgenomen voertuigroute wijkt af of kan niet worden gereden. Controleer het routeoverzicht.','A übernommene Autoroute weicht ab oder geht si ned aus. Schau bitte de Routenübersicht an.'),
    }
    index = {'en':0,'nl':1,'de-AT':2}[language]
    if data.get('title') in titles:
        data['title'] = titles[data['title']][index]
    body = data.get('body','')
    templates = {
        'friend_request': ('{name} wants to connect with you.','{name} wil contact met je maken.','{name} mag si mit dir verbinden.'),
        'trip_invite': ('You are invited to the trip “{title}”.','Je bent uitgenodigd voor de rit ‘{title}’.','Du bist zur Fahrt „{title}“ eingladn.'),
        'chat': ('{name}: new message in “{title}”.','{name}: nieuw bericht in ‘{title}’.','{name}: neue Nachricht in „{title}“.'),
    }
    template = templates.get(data.pop('message_key',None))
    parameters = data.pop('parameters',{})
    if template:
        data['body'] = template[index].format(**parameters)[:200]
    elif body in bodies:
        data['body'] = bodies[body][index]
    elif body.endswith(' möchte sich mit dir verbinden.'):
        data['body'] = templates['friend_request'][index].format(name=body[:-len(' möchte sich mit dir verbinden.')])
    elif body.startswith('Du bist zur Fahrt „') and body.endswith('“ eingeladen.'):
        title = body[len('Du bist zur Fahrt „'):-len('“ eingeladen.')]
        data['body'] = templates['trip_invite'][index].format(title=title)
    elif ': neue Nachricht in „' in body and body.endswith('“.'):
        name, title = body.rsplit(': neue Nachricht in „',1)
        data['body'] = templates['chat'][index].format(name=name,title=title[:-2])
    return json.dumps(data,ensure_ascii=False)


class NoRedirectSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def deliver(data, payload):
    with NoRedirectSession() as session:
        subscription = {key:data[key] for key in ('endpoint','keys')}
        return webpush(subscription_info=subscription, data=payload, requests_session=session,
                       vapid_private_key=settings.vapid_private_key,
                       vapid_claims={'sub':settings.vapid_subject}, ttl=3600, timeout=10,
                       headers={'Urgency':'high'})


def validate_subscription(subscription):
    try:
        url = urlsplit(subscription['endpoint'])
        host = url.hostname or ''
        allowed = host in {'fcm.googleapis.com', 'web.push.apple.com', 'updates.push.services.mozilla.com'} or host.endswith('.push.services.mozilla.com')
        valid_url = url.scheme == 'https' and allowed and url.port in (None, 443) and not url.username and not url.password and not url.fragment
        keys = subscription['keys']
        if not all(re.fullmatch(r'[A-Za-z0-9_-]{16,100}={0,2}', keys.get(key,'')) for key in ('p256dh','auth')):
            raise ValueError('Invalid encoding')
        public = base64.urlsafe_b64decode(keys.get('p256dh', '') + '=' * (-len(keys.get('p256dh', '')) % 4))
        auth = base64.urlsafe_b64decode(keys.get('auth', '') + '=' * (-len(keys.get('auth', '')) % 4))
        valid_keys = len(public) == 65 and public[0] == 4 and len(auth) == 16
    except (ValueError, TypeError):
        valid_url = valid_keys = False
    if not valid_url or not valid_keys:
        raise HTTPException(422, 'Ungültiges Push-Abonnement. Apple, Firefox und Chromium werden unterstützt.')
    return {'endpoint': subscription['endpoint'], 'keys': {'p256dh': keys['p256dh'], 'auth': keys['auth']}}


def subscribe(subscription, identity, session_token):
    if not settings.push_ready:
        raise HTTPException(503, 'Web-Push ist noch nicht eingerichtet.')
    data = validate_subscription(subscription)
    language = subscription.get('language')
    if language in ('de','en','nl','de-AT'):
        data['language'] = language
    endpoint_hash, session_hash = digest(data['endpoint']), digest(session_token)
    if not db.one('SELECT token_hash FROM sessions WHERE token_hash=? AND user_id=? AND kind=?', (session_hash, identity.user['id'], 'user')):
        raise HTTPException(403, 'Push-Abonnements benötigen eine Browser-Anmeldung.')
    existing = db.one('SELECT * FROM push_subscriptions WHERE endpoint_hash=?', (endpoint_hash,))
    if existing and existing['user_id'] != identity.user['id']:
        raise HTTPException(409, 'Bitte die bisherigen Benachrichtigungen auf diesem Gerät zuerst deaktivieren.')
    if existing and language is None:
        previous = json.loads(cipher().decrypt(existing['encrypted_subscription'].encode()))
        if previous.get('language') in ('de','en','nl','de-AT'):
            data['language'] = previous['language']
    count = db.one('SELECT count(*) AS n FROM push_subscriptions WHERE user_id=? AND expires_at>?', (identity.user['id'], time.time()))['n']
    if count >= 8 and not existing:
        raise HTTPException(409, 'Höchstens acht Geräte pro Konto sind erlaubt.')
    encrypted = cipher().encrypt(json.dumps(data).encode()).decode()
    db.execute('INSERT INTO push_subscriptions VALUES (?,?,?,?,?) ON CONFLICT(endpoint_hash) DO UPDATE SET session_hash=excluded.session_hash,encrypted_subscription=excluded.encrypted_subscription,expires_at=excluded.expires_at',
               (endpoint_hash, identity.user['id'], session_hash, encrypted, identity.expires_at))


async def test_message(endpoint, identity, session_token):
    if not settings.push_ready:
        raise HTTPException(503, 'Web-Push ist noch nicht eingerichtet.')
    subscription = db.one('SELECT * FROM push_subscriptions WHERE endpoint_hash=? AND user_id=? AND session_hash=? AND expires_at>?',
                          (digest(endpoint), identity.user['id'], digest(session_token), time.time()))
    if not subscription:
        raise HTTPException(404, 'Dieses Browser-Abonnement ist nicht registriert. Benachrichtigungen im Profil erneut abgleichen.')
    # Every tap is a distinct diagnostic alert, rather than a replacement of a
    # previous test notification in the device's notification center.
    payload = json.dumps({'title':'TeslaTalk · Testnachricht','body':'Deine Benachrichtigungen erreichen dieses Gerät.', 'url':'/', 'tag':'teslatalk-test-'+secrets.token_hex(8)})
    started = time.perf_counter()
    try:
        data = json.loads(cipher().decrypt(subscription['encrypted_subscription'].encode()))
        await asyncio.to_thread(deliver, data, localize_payload(payload, data.get('language','de')))
    except WebPushException as error:
        status = error.response.status_code if error.response is not None else 0
        if status in (404, 410):
            db.execute('DELETE FROM push_subscriptions WHERE endpoint_hash=?', (subscription['endpoint_hash'],))
            raise HTTPException(410, 'Das Browser-Abonnement ist abgelaufen. Benachrichtigungen erneut aktivieren.') from None
        raise HTTPException(502, f'Der Push-Dienst hat die Testnachricht abgelehnt (HTTP {status or "unbekannt"}). VAPID-Konfiguration und Verbindung prüfen.') from None
    except Exception:
        raise HTTPException(502, 'Der Push-Dienst ist gerade nicht erreichbar. Bitte erneut versuchen.') from None
    return {'provider_accepted_at':time.time(), 'provider_elapsed_ms':round((time.perf_counter()-started)*1000)}


def test_all_devices():
    if not settings.push_ready:
        raise HTTPException(503, 'Web-Push ist noch nicht eingerichtet.')
    now = time.time()
    payload = json.dumps({'title':'TeslaTalk · Server-Testnachricht',
                          'body':'Deine TeslaTalk-Administration testet die Benachrichtigungen.',
                          'url':'/', 'tag':'teslatalk-admin-test-'+secrets.token_hex(8)})
    with db.connect() as connection:
        recipients = connection.execute('''
            SELECT p.user_id, m.trip_id, count(DISTINCT p.endpoint_hash) AS devices
            FROM push_subscriptions p
            JOIN sessions s ON s.token_hash=p.session_hash AND s.user_id=p.user_id AND s.kind='user'
            JOIN users u ON u.id=p.user_id
            LEFT JOIN members m ON u.provider='guest' AND m.user_id=p.user_id AND m.left_at IS NULL
            LEFT JOIN trips t ON t.id=m.trip_id
            WHERE p.expires_at>? AND s.expires_at>?
              AND (u.provider!='guest' OR (t.starts_at<=? AND t.ends_at>? AND t.finished_at IS NULL))
            GROUP BY p.user_id, m.trip_id
        ''', (now, now, now, now)).fetchall()
        connection.executemany('INSERT INTO push_outbox(user_id,trip_id,payload,next_at,expires_at) VALUES (?,?,?,?,?)',
                               [(row['user_id'],row['trip_id'],payload,now,now+3600) for row in recipients])
    return {'ok':True, 'queued_accounts':len(recipients), 'queued_devices':sum(row['devices'] for row in recipients)}


def enqueue(user_id, body, url='/', tag='teslatalk', trip_id=None, *, message_key=None, parameters=None):
    if not settings.push_ready or not db.one('SELECT endpoint_hash FROM push_subscriptions WHERE user_id=? AND expires_at>?', (user_id, time.time())):
        return
    # No chat contents, location or plates in lock-screen notifications.
    content = {'title': 'TeslaTalk', 'body': body[:200], 'url': url, 'tag': tag}
    if message_key:
        content.update(message_key=message_key,parameters=parameters or {})
    payload = json.dumps(content)
    db.execute('INSERT INTO push_outbox(user_id,trip_id,payload,next_at,expires_at) VALUES (?,?,?,?,?)',
               (user_id, trip_id, payload, time.time(), time.time()+3600))


def eligible(job):
    if not job['trip_id']:
        return True
    row = db.one('SELECT t.starts_at,t.ends_at,t.finished_at,m.left_at,u.provider FROM trips t JOIN members m ON m.trip_id=t.id JOIN users u ON u.id=m.user_id WHERE t.id=? AND m.user_id=?', (job['trip_id'], job['user_id']))
    if not row or row['left_at'] is not None or time.time() >= min(row['ends_at'], row['finished_at'] or row['ends_at']):
        return False
    return row['provider'] != 'guest' or time.time() >= row['starts_at']


async def send_job_device(job, endpoint_hash, slots):
    async with slots:
        # Consent and trip lifetime can change while a delivery waits for a slot.
        if time.time() >= job['expires_at'] or not eligible(job):
            return False
        subscription = db.one('SELECT * FROM push_subscriptions WHERE endpoint_hash=? AND user_id=? AND expires_at>?',
                              (endpoint_hash,job['user_id'],time.time()))
        if not subscription:
            return False
        try:
            data = json.loads(cipher().decrypt(subscription['encrypted_subscription'].encode()))
            await asyncio.to_thread(deliver, data, localize_payload(job['payload'], data.get('language','de')))
            # Successful devices must not receive the same alert again when another
            # device needs a retry. Receipts expire together with their outbox job.
            db.execute('INSERT OR IGNORE INTO push_deliveries(job_id,endpoint_hash) SELECT id,? FROM push_outbox WHERE id=?',
                       (endpoint_hash,job['id']))
        except WebPushException as error:
            status = error.response.status_code if error.response is not None else 0
            if status in (404, 410):
                db.execute('DELETE FROM push_subscriptions WHERE endpoint_hash=?', (endpoint_hash,))
            else:
                return True
        except Exception:
            # Never log subscription endpoints, encryption keys or VAPID secrets.
            return True
        return False


async def send_ordered(job, endpoint_hash, slots, device_locks):
    # Keep queued messages in order on each device while other devices run freely.
    async with device_locks.setdefault(endpoint_hash,asyncio.Lock()):
        return await send_job_device(job,endpoint_hash,slots)


async def process_job(job, slots, device_locks):
    if not eligible(job):
        db.execute('DELETE FROM push_outbox WHERE id=?', (job['id'],))
        return
    devices = db.all_rows('''SELECT p.endpoint_hash FROM push_subscriptions p
        WHERE p.user_id=? AND p.expires_at>?
          AND NOT EXISTS (SELECT 1 FROM push_deliveries d WHERE d.job_id=? AND d.endpoint_hash=p.endpoint_hash)''',
        (job['user_id'],time.time(),job['id']))
    results = await asyncio.gather(*(send_ordered(job,device['endpoint_hash'],slots,device_locks) for device in devices))
    if any(results) and job['attempts'] < 2 and time.time() < job['expires_at']:
        db.execute('UPDATE push_outbox SET attempts=attempts+1,next_at=? WHERE id=?', (time.time()+30*2**job['attempts'], job['id']))
    else:
        db.execute('DELETE FROM push_outbox WHERE id=?', (job['id'],))


async def process_outbox():
    now = time.time()
    db.execute('DELETE FROM push_subscriptions WHERE expires_at<=?', (now,))
    db.execute('DELETE FROM push_outbox WHERE expires_at<=?', (now,))
    jobs = db.all_rows('SELECT * FROM push_outbox WHERE next_at<=? ORDER BY id LIMIT 20', (now,))
    slots = asyncio.Semaphore(MAX_DELIVERIES)
    device_locks = {}
    await asyncio.gather(*(process_job(job,slots,device_locks) for job in jobs))


async def worker():
    while True:
        try:
            if settings.push_ready:
                await process_outbox()
        except Exception as error:
            # A temporary failure must not permanently stop the persistent queue.
            # Exception messages may contain private endpoint or database details.
            log.warning('Push processing unavailable: %s', type(error).__name__)
        await asyncio.sleep(2)
