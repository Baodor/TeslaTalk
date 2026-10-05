import sqlite3
from urllib.parse import parse_qs, urlsplit
import httpx
from app import db, fleet
from app.config import settings

AVATAR = 'https://vehicle-files.prd.euw1.vn.cloud.tesla.com/profile_images/test.jpg'


def test_existing_volume_migration_keeps_users_and_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / 'old.sqlite'
    monkeypatch.setattr(settings, 'db_path', str(path))
    with sqlite3.connect(path) as connection:
        connection.executescript(db.SCHEMA.replace(', avatar_url TEXT', ''))
        connection.execute('INSERT INTO users(id,provider,subject,username,display_name,created_at) VALUES (?,?,?,?,?,?)',
                           ('existing', 'tesla', 'tesla:existing', 'driver', 'Existing driver', 123))
    db.initialize()
    db.initialize()
    account = db.one('SELECT * FROM users WHERE id=?', ('existing',))
    assert account['display_name'] == 'Existing driver' and account['created_at'] == 123
    assert account['avatar_url'] is None


def test_tesla_login_saves_account_picture(client, monkeypatch):
    monkeypatch.setattr(settings, 'tesla_client_id', 'test-client')
    monkeypatch.setattr(settings, 'tesla_client_secret', 'test-secret')

    class TeslaClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            return httpx.Response(200, json={'access_token': 'test-access', 'refresh_token': 'test-refresh', 'expires_in': 300})

        async def get(self, url, **kwargs):
            assert url.endswith('/api/1/users/me')
            return httpx.Response(200, json={'response': {'id': 'tesla-test-user', 'email': 'test@example.com', 'full_name': 'Tesla Driver', 'profile_image_url': AVATAR}})

    monkeypatch.setattr('app.main.httpx.AsyncClient', TeslaClient)
    redirect = client.get('/auth/tesla', follow_redirects=False)
    state = parse_qs(urlsplit(redirect.headers['location']).query)['state'][0]
    response = client.get('/auth/tesla/callback', params={'state': state, 'code': 'test-code'}, follow_redirects=False)
    assert response.status_code == 303
    account = client.get('/api/me').json()
    assert account['avatar_url'] == AVATAR
    assert account['display_name'] == 'Tesla Driver'
    assert account['needs_username'] is True
    assert client.patch('/api/me',json={'username':'MyTeslaUsername','display_name':account['display_name']}).status_code==200
    assert client.get('/api/me').json()['needs_username'] is False
    redirect = client.get('/auth/tesla', follow_redirects=False)
    state = parse_qs(urlsplit(redirect.headers['location']).query)['state'][0]
    assert client.get('/auth/tesla/callback',params={'state':state,'code':'another-test-code'},follow_redirects=False).status_code==303
    again=client.get('/api/me').json()
    assert again['id']==account['id'] and again['username']=='MyTeslaUsername'
    assert again['needs_username'] is False
    assert 'profile_image_url' not in account and 'test-access' not in str(account)


def test_profile_refresh_loads_tesla_image_and_exposes_it_on_trip(owner, monkeypatch):
    user = owner.get('/api/me').json()
    db.execute("UPDATE users SET provider='tesla' WHERE id=?", (user['id'],))

    async def account(user_id, path):
        assert user_id == user['id'] and path == '/api/1/users/me'
        return {'profile_image_url': AVATAR}

    monkeypatch.setattr(fleet, 'request', account)
    assert owner.post('/api/me/tesla-profile').json()['avatar_url'] == AVATAR
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    trip = owner.post('/api/trips', json={'title': 'Avatar test', 'starts_at': (now - timedelta(minutes=1)).isoformat(), 'ends_at': (now + timedelta(hours=1)).isoformat()}).json()
    assert owner.get('/api/trips/' + trip['id']).json()['participants_detail'][0]['avatar_url'] == AVATAR
    assert owner.get('/api/me').json()['avatar_url'] == AVATAR
