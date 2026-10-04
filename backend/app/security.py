import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from fastapi import HTTPException, Request
from cryptography.fernet import Fernet
from .config import settings
from . import db


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def join_pin_hash(pin):
    return hmac.new(settings.secret.encode(), pin.encode(), hashlib.sha256).hexdigest()


def pin_hash(pin):
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', pin.encode(), salt.encode(), 200_000).hex()
    return salt + ':' + value


def pin_matches(pin, stored):
    salt, value = stored.split(':')
    actual = hashlib.pbkdf2_hmac('sha256', pin.encode(), salt.encode(), 200_000).hex()
    return hmac.compare_digest(actual, value)


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.secret.encode()).digest()))


@dataclass
class Identity:
    user: dict
    expires_at: float
    kind: str = 'user'


def authenticate(headers, cookies, admin=False):
    authorization = headers.get('authorization', '')
    if authorization:
        if admin or not authorization.startswith('Bearer '):
            raise HTTPException(401, 'Ungültiger API-Schlüssel.')
        row = db.one('SELECT * FROM api_keys WHERE token_hash=? AND (expires_at=0 OR expires_at>?)', (digest(authorization[7:]), time.time()))
        if not row:
            raise HTTPException(401, 'API-Schlüssel ungültig oder abgelaufen.')
    else:
        cookie = cookies.get('tt_admin' if admin else 'tt_session', '')
        row = db.one('SELECT * FROM sessions WHERE token_hash=? AND expires_at>? AND kind=?', (digest(cookie), time.time(), 'admin' if admin else 'user'))
        if not row:
            raise HTTPException(401, 'Bitte anmelden.')
    if admin:
        return Identity({'id': row['user_id']}, row['expires_at'], 'admin')
    user = db.one('SELECT * FROM users WHERE id=?', (row['user_id'],))
    if not user:
        raise HTTPException(401, 'Konto nicht vorhanden.')
    # Zero is the persistent sentinel for non-expiring API keys. Keep internal
    # deadline comparisons working; trip/guest deadlines still apply separately.
    expiry = float('inf') if authorization and row['expires_at'] == 0 else row['expires_at']
    return Identity(user, expiry)


def current_user(request: Request):
    return authenticate(request.headers, request.cookies)


def current_admin(request: Request):
    return authenticate(request.headers, request.cookies, admin=True)


def driver(identity):
    if identity.user['provider'] == 'guest':
        raise HTTPException(403, 'Diese Funktion ist nur für Fahrer verfügbar.')


def set_session(response, user_id, expires_at=None, admin=False):
    token = secrets.token_urlsafe(32)
    expiry = expires_at or time.time() + 7 * 86400
    db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(token), user_id, 'admin' if admin else 'user', expiry))
    response.set_cookie('tt_admin' if admin else 'tt_session', token, max_age=max(0, int(expiry-time.time())), httponly=True, secure=settings.secure, samesite='lax', path='/')


def user_public(user):
    return {key: user.get(key) for key in ('id', 'username', 'display_name', 'plate', 'favorite_vehicle', 'provider')}


class RateLimiter:
    def __init__(self):
        self.windows = defaultdict(deque)

    def check(self, key, limit=30, seconds=60):
        now = time.time()
        window = self.windows[key]
        while window and window[0] <= now-seconds:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(429, 'Zu viele Versuche. Bitte kurz warten.')
        window.append(now)
        if len(self.windows) > 10000:
            self.windows = defaultdict(deque, {k:v for k,v in self.windows.items() if v and v[-1] > now-3600})


limiter = RateLimiter()
