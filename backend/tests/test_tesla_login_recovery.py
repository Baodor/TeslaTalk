from urllib.parse import parse_qs,urlparse
from fastapi.testclient import TestClient
from app import db,main
from app.config import settings
from app.main import app
from app.security import digest


def start(client,monkeypatch):
    monkeypatch.setattr(settings,'tesla_client_id','isolated-client')
    monkeypatch.setattr(settings,'tesla_client_secret','isolated-secret')
    response=client.get('/auth/tesla',follow_redirects=False)
    return parse_qs(urlparse(response.headers['location']).query)['state'][0]


def test_two_login_attempts_in_one_browser_keep_independent_pkce_bindings(client,monkeypatch):
    first=start(client,monkeypatch);second=start(client,monkeypatch)
    assert first!=second
    assert client.get('/auth/tesla/callback',params={'state':first},follow_redirects=False).status_code==307
    assert client.get('/auth/tesla/callback',params={'state':second},follow_redirects=False).status_code==307
    assert not db.one('SELECT * FROM oauth_states')


def test_cookie_loss_keeps_state_unconsumed_and_returns_utf8_recovery_page(client,monkeypatch):
    state=start(client,monkeypatch)
    lost=TestClient(app)
    response=lost.get('/auth/tesla/callback',params={'state':state,'code':'not-exchanged'})
    assert response.status_code==400
    assert response.headers['content-type']=='text/html; charset=utf-8'
    assert 'ungültig' in response.text and 'ungÃ' not in response.text
    assert 'href="/auth/tesla"' in response.text
    assert db.one('SELECT * FROM oauth_states WHERE state_hash=?',(digest(state),))
    assert not db.one('SELECT * FROM credentials')


def test_stale_callback_with_valid_session_goes_home_without_token_exchange(owner,monkeypatch):
    async def forbidden(*args,**kwargs):raise AssertionError('Code exchanged twice')
    monkeypatch.setattr(main.httpx.AsyncClient,'post',forbidden)
    response=owner.get('/auth/tesla/callback',params={'state':'stale-state','code':'old-code'},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']=='/'
    assert owner.get('/api/me').status_code==200
    assert not db.one('SELECT * FROM credentials')


def test_expired_login_does_not_create_or_change_a_session(client,monkeypatch):
    state=start(client,monkeypatch)
    db.execute('UPDATE oauth_states SET expires_at=0')
    response=client.get('/auth/tesla/callback',params={'state':state,'code':'never-exchanged'},follow_redirects=False)
    assert response.status_code==400
    assert client.get('/api/me').status_code==401


def test_login_from_lan_address_moves_to_callback_host_before_binding_cookie(client,monkeypatch):
    monkeypatch.setattr(settings,'app_url','https://teslatalk.example.test')
    response=client.get('/auth/tesla',headers={'host':'192.168.1.23'},follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location']=='https://teslatalk.example.test/auth/tesla'
    assert not db.one('SELECT * FROM oauth_states')
    assert 'set-cookie' not in response.headers
