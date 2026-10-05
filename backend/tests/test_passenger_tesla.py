import time
from datetime import datetime,timedelta,timezone
from urllib.parse import parse_qs,urlsplit
import httpx
import pytest
from fastapi.testclient import TestClient
from app import db
from app.config import settings
from app.main import app

AVATAR='https://images.example.test/passenger.jpg'


def guest_trip(owner):
    now=datetime.now(timezone.utc)
    trip=owner.post('/api/trips',json={'title':'Passenger profile','starts_at':(now-timedelta(minutes=1)).isoformat(),'ends_at':(now+timedelta(hours=1)).isoformat()}).json()
    key=owner.get('/api/trips/'+trip['id']).json()['guest_url'].split('/')[-1]
    guest=TestClient(app,headers={'origin':'http://testserver'})
    assert guest.post('/api/guest/'+key+'/register',json={'name':'Anna','pin':'012345'}).status_code==200
    return guest,trip,key


def fake_tesla(monkeypatch):
    monkeypatch.setattr(settings,'tesla_client_id','test-client')
    monkeypatch.setattr(settings,'tesla_client_secret','test-secret')
    calls=[]
    class TeslaClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            calls.append(('POST',url))
            return httpx.Response(200,json={'access_token':'profile-only-token','refresh_token':'must-not-be-saved'})
        async def get(self,url,**kwargs):
            calls.append(('GET',url))
            assert url.endswith('/api/1/users/me')
            return httpx.Response(200,json={'response':{'id':'same-tesla-as-driver','email':'anna@example.test','full_name':'Different Tesla Name','profile_image_url':AVATAR}})
    monkeypatch.setattr('app.main.httpx.AsyncClient',TeslaClient)
    return calls


def start(guest,trip):
    response=guest.get('/auth/tesla/passenger',params={'trip_id':trip['id']},follow_redirects=False)
    assert response.status_code==307,response.text
    params=parse_qs(urlsplit(response.headers['location']).query)
    assert params['scope']==['openid user_data']
    return params['state'][0]


def test_profile_link_preserves_guest_identity_pin_deadline_and_excludes_car(owner,monkeypatch):
    calls=fake_tesla(monkeypatch)
    guest,trip,key=guest_trip(owner)
    me=guest.get('/api/me').json()
    before=db.one("SELECT expires_at FROM sessions WHERE user_id=? AND kind='user'",(me['id'],))['expires_at']
    db.execute("INSERT INTO users(id,provider,subject,username,display_name,created_at) VALUES ('existing-driver','tesla','tesla:same-tesla-as-driver','TeslaOwner','Existing driver',?)",(time.time(),))
    state=start(guest,trip)
    response=guest.get('/auth/tesla/callback',params={'state':state,'code':'test'},follow_redirects=False)
    assert response.status_code==303,response.text
    assert response.headers['location']=='/trip/'+trip['id']
    linked=guest.get('/api/me').json()
    assert linked['id']==me['id'] and linked['provider']=='guest' and linked['display_name']=='Anna'
    assert linked['tesla_profile_linked'] is True and linked['avatar_url']==AVATAR
    assert linked['needs_username'] is False
    assert db.one('SELECT email FROM users WHERE id=?',(me['id'],))['email']=='anna@example.test'
    assert db.one("SELECT expires_at FROM sessions WHERE user_id=? AND kind='user'",(me['id'],))['expires_at']==before
    assert db.one('SELECT count(*) n FROM credentials')['n']==0
    assert db.one('SELECT count(*) n FROM vehicles WHERE user_id=?',(me['id'],))['n']==0
    detail=owner.get('/api/trips/'+trip['id']).json()
    passenger=next(p for p in detail['participants_detail'] if p['id']==me['id'])
    assert passenger['role']=='passenger' and passenger['vehicle_id'] is None and passenger['data']=={}
    assert passenger['avatar_url']==AVATAR
    assert me['id'] not in [v['user_id'] for v in detail['route_overview']['vehicles']]
    for path in ['/api/vehicles','/api/keys']:
        assert guest.get(path).status_code==403
    assert guest.post('/api/trips/'+trip['id']+'/route/accept').status_code==403
    assert db.one('SELECT display_name FROM users WHERE id=?',('existing-driver',))['display_name']=='Existing driver'
    assert len(calls)==2
    assert guest.post('/auth/logout').status_code==200
    assert guest.post('/api/guest/'+key+'/login',json={'name':'Anna','pin':'012345'}).status_code==200
    assert guest.get('/api/me').json()['avatar_url']==AVATAR
    assert guest.delete('/api/me/tesla-profile-link').status_code==200
    unlinked=guest.get('/api/me').json()
    assert unlinked['provider']=='guest' and unlinked['avatar_url'] is None and not unlinked['tesla_profile_linked']


@pytest.mark.parametrize('change',['logout','trip_finished','session_swapped'])
def test_callback_rejects_changed_or_expired_guest_before_tesla_request(owner,monkeypatch,change):
    calls=fake_tesla(monkeypatch)
    guest,trip,_=guest_trip(owner)
    uid=guest.get('/api/me').json()['id']
    state=start(guest,trip)
    if change=='logout':guest.post('/auth/logout')
    elif change=='trip_finished':db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),trip['id']))
    else:guest.cookies.set('tt_session',owner.cookies.get('tt_session'))
    response=guest.get('/auth/tesla/callback',params={'state':state,'code':'test'},follow_redirects=False)
    assert response.status_code in (400,401,403),response.text
    assert not calls and not db.one('SELECT * FROM tesla_profile_links WHERE user_id=?',(uid,))
    assert db.one('SELECT provider FROM users WHERE id=?',(uid,))['provider']=='guest'


def test_deleted_guest_during_token_exchange_cannot_be_restored(owner,monkeypatch):
    fake_tesla(monkeypatch)
    guest,trip,_=guest_trip(owner)
    uid=guest.get('/api/me').json()['id']
    state=start(guest,trip)
    from app.main import httpx as main_httpx
    original=main_httpx.AsyncClient.get
    async def deleted_get(self,url,**kwargs):
        profile=await original(self,url,**kwargs)
        from app.accounts import delete_user
        delete_user(uid,db.one('SELECT username FROM users WHERE id=?',(uid,))['username'])
        return profile
    monkeypatch.setattr(main_httpx.AsyncClient,'get',deleted_get)
    response=guest.get('/auth/tesla/callback',params={'state':state,'code':'test'},follow_redirects=False)
    assert response.status_code==401
    assert not db.one('SELECT * FROM users WHERE id=?',(uid,))
    assert not db.one('SELECT * FROM tesla_profile_links WHERE user_id=?',(uid,))


def test_driver_cannot_use_passenger_profile_link(owner,monkeypatch):
    fake_tesla(monkeypatch)
    _,trip,_=guest_trip(owner)
    assert owner.get('/auth/tesla/passenger',params={'trip_id':trip['id']}).status_code==403
