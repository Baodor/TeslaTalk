"""Opt-in Web Push, encrypted subscriptions and a bounded persistent outbox."""
import asyncio
import base64
import json
import re
import time
from urllib.parse import urlsplit
from fastapi import HTTPException
from pywebpush import webpush, WebPushException
import requests
from . import db
from .config import settings
from .security import cipher, digest


class NoRedirectSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def deliver(data, payload):
    with NoRedirectSession() as session:
        return webpush(subscription_info=data, data=payload, requests_session=session,
                       vapid_private_key=settings.vapid_private_key,
                       vapid_claims={'sub':settings.vapid_subject}, ttl=3600, timeout=10)


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
    endpoint_hash, session_hash = digest(data['endpoint']), digest(session_token)
    if not db.one('SELECT token_hash FROM sessions WHERE token_hash=? AND user_id=? AND kind=?', (session_hash, identity.user['id'], 'user')):
        raise HTTPException(403, 'Push-Abonnements benötigen eine Browser-Anmeldung.')
    existing = db.one('SELECT * FROM push_subscriptions WHERE endpoint_hash=?', (endpoint_hash,))
    if existing and existing['user_id'] != identity.user['id']:
        raise HTTPException(409, 'Bitte die bisherigen Benachrichtigungen auf diesem Gerät zuerst deaktivieren.')
    count = db.one('SELECT count(*) AS n FROM push_subscriptions WHERE user_id=? AND expires_at>?', (identity.user['id'], time.time()))['n']
    if count >= 8 and not existing:
        raise HTTPException(409, 'Höchstens acht Geräte pro Konto sind erlaubt.')
    encrypted = cipher().encrypt(json.dumps(data).encode()).decode()
    db.execute('INSERT INTO push_subscriptions VALUES (?,?,?,?,?) ON CONFLICT(endpoint_hash) DO UPDATE SET session_hash=excluded.session_hash,encrypted_subscription=excluded.encrypted_subscription,expires_at=excluded.expires_at',
               (endpoint_hash, identity.user['id'], session_hash, encrypted, identity.expires_at))


def enqueue(user_id, body, url='/', tag='teslatalk', trip_id=None):
    if not settings.push_ready or not db.one('SELECT endpoint_hash FROM push_subscriptions WHERE user_id=? AND expires_at>?', (user_id, time.time())):
        return
    # No chat contents, location or plates in lock-screen notifications.
    payload = json.dumps({'title': 'TeslaTalk', 'body': body[:200], 'url': url, 'tag': tag})
    db.execute('INSERT INTO push_outbox(user_id,trip_id,payload,next_at,expires_at) VALUES (?,?,?,?,?)',
               (user_id, trip_id, payload, time.time(), time.time()+3600))


def eligible(job):
    if not job['trip_id']:
        return True
    row = db.one('SELECT t.starts_at,t.ends_at,t.finished_at,m.left_at,u.provider FROM trips t JOIN members m ON m.trip_id=t.id JOIN users u ON u.id=m.user_id WHERE t.id=? AND m.user_id=?', (job['trip_id'], job['user_id']))
    if not row or row['left_at'] is not None or time.time() >= min(row['ends_at'], row['finished_at'] or row['ends_at']):
        return False
    return row['provider'] != 'guest' or time.time() >= row['starts_at']


async def process_outbox():
    now = time.time()
    db.execute('DELETE FROM push_subscriptions WHERE expires_at<=?', (now,))
    db.execute('DELETE FROM push_outbox WHERE expires_at<=?', (now,))
    for job in db.all_rows('SELECT * FROM push_outbox WHERE next_at<=? ORDER BY id LIMIT 20', (now,)):
        if not eligible(job):
            db.execute('DELETE FROM push_outbox WHERE id=?', (job['id'],))
            continue
        retry = False
        for subscription in db.all_rows('SELECT * FROM push_subscriptions WHERE user_id=? AND expires_at>?', (job['user_id'], time.time())):
            # Recheck scheduled expiry immediately before sending, including queued jobs.
            if not eligible(job):
                break
            try:
                data = json.loads(cipher().decrypt(subscription['encrypted_subscription'].encode()))
                await asyncio.to_thread(deliver, data, job['payload'])
            except WebPushException as error:
                status = error.response.status_code if error.response is not None else 0
                if status in (404, 410):
                    db.execute('DELETE FROM push_subscriptions WHERE endpoint_hash=?', (subscription['endpoint_hash'],))
                else:
                    retry = True
            except Exception:
                # Never log subscription endpoints, encryption keys or VAPID secrets.
                retry = True
        if retry and job['attempts'] < 2:
            db.execute('UPDATE push_outbox SET attempts=attempts+1,next_at=? WHERE id=?', (time.time()+30*2**job['attempts'], job['id']))
        else:
            db.execute('DELETE FROM push_outbox WHERE id=?', (job['id'],))


async def worker():
    while True:
        if settings.push_ready:
            await process_outbox()
        await asyncio.sleep(2)
