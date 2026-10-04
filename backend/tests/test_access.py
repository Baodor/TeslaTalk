import time
from datetime import datetime,timezone
import pytest
import jwt
from app import db
from app.config import settings
from app.main import album_name
from app.security import cipher
from .conftest import new_driver


def trip(owner, start=None, end=None):
    now=time.time()
    result=owner.post('/api/trips',json={'title':'Roadtrip ans Meer','destination':'Hamburg',
        'starts_at':datetime.fromtimestamp(start or now-60,timezone.utc).isoformat(),
        'ends_at':datetime.fromtimestamp(end or now+3600,timezone.utc).isoformat()})
    assert result.status_code==200,result.text
    return result.json()


def passenger(owner, created, name='Mitfahrer'):
    detail=owner.get('/api/trips/'+created['id']).json()
    pin=owner.post('/api/trips/'+created['id']+'/passengers',json={'name':name}).json()['pin']
    guest=new_driver('Unused')
    guest.cookies.clear()
    key=detail['guest_url'].split('/')[-1]
    assert guest.post('/api/guest/'+key+'/login',json={'name':name,'pin':pin}).status_code==200
    return guest,key,pin


def test_cross_trip_access_and_ws_rejected(owner):
    created=trip(owner)
    stranger=new_driver('Fremder')
    root='/api/trips/'+created['id']
    for suffix in ('','/messages','/history','/ranking','/export'):
        assert stranger.get(root+suffix).status_code==404
    assert stranger.post(root+'/messages',json={'text':'Nicht erlaubt'}).status_code==404
    assert stranger.post(root+'/voice-token').status_code==404
    with pytest.raises(Exception):
        with stranger.websocket_connect('/api/ws/trips/'+created['id'],headers={'origin':'http://testserver'}):
            pass


def test_driver_join_friend_and_invitation(owner):
    created=trip(owner)
    friend=new_driver('Freund')
    friend_user=friend.get('/api/me').json()
    leader_user=owner.get('/api/me').json()
    assert owner.post('/api/friends',json={'query':friend_user['username']}).status_code==200
    incoming=friend.get('/api/friends').json()[0]
    assert incoming['incoming'] and incoming['status']=='pending'
    assert owner.post('/api/friends/'+friend_user['id']+'/accept').status_code==404
    assert friend.post('/api/friends/'+leader_user['id']+'/accept').status_code==200
    assert owner.post('/api/trips/'+created['id']+'/invite',json={'query':friend_user['username']}).status_code==200
    assert friend.get('/api/invites').json()[0]['id']==created['id']
    assert friend.post('/api/trips/'+created['id']+'/accept').status_code==200
    assert friend.get('/api/invites').json()==[]
    other=new_driver('Zweiter Fahrer')
    assert other.post('/api/trips/join',json={'pin':created['pin']}).status_code==200


def test_passenger_name_pin_and_driver_privileges(owner):
    created=trip(owner)
    guest,key,pin=passenger(owner,created)
    root='/api/trips/'+created['id']
    assert guest.get('/api/me').json()['provider']=='guest'
    assert guest.get(root).status_code==200
    assert guest.post(root+'/messages',json={'text':'Hallo Fahrer!'}).status_code==200
    assert guest.post(root+'/finish').status_code==403
    assert guest.post('/api/keys',json={'label':'Verboten'}).status_code==403
    assert guest.post(root+'/samples',json={'latitude':50,'longitude':8,'source':'browser'}).status_code==403
    guest.cookies.clear()
    assert guest.post('/api/guest/'+key+'/login',json={'name':'Nicht eingeladen','pin':pin}).status_code==401
    assert guest.post('/api/guest/'+key+'/login',json={'name':'Mitfahrer','pin':'999999' if pin!='999999' else '000000'}).status_code==401


def test_period_boundaries_and_upload_gate(owner):
    created=trip(owner)
    guest,key,pin=passenger(owner,created)
    db.execute('UPDATE trips SET ends_at=? WHERE id=?',(time.time()-1,created['id']))
    root='/api/trips/'+created['id']
    assert guest.get(root).status_code==403
    assert guest.post(root+'/messages',json={'text':'Zu spät'}).status_code==403
    assert guest.post('/api/guest/'+key+'/login',json={'name':'Mitfahrer','pin':pin}).status_code==403
    assert owner.post(root+'/samples',json={'latitude':50,'longitude':8,'source':'browser'}).status_code==403
    assert owner.post(root+'/messages',json={'text':'Zu spät'}).status_code==403
    planned=trip(owner,start=time.time()+300,end=time.time()+900)
    assert owner.post('/api/trips/'+planned['id']+'/voice-token').status_code==403


def test_public_share_is_read_only_revocable_and_private_data_absent(owner):
    created=trip(owner)
    root='/api/trips/'+created['id']
    assert owner.post(root+'/share').status_code==403
    assert owner.post(root+'/messages',json={'text':'Private Nachricht'}).status_code==200
    assert owner.post(root+'/finish').status_code==200
    url=owner.post(root+'/share').json()['url']
    public=owner.get('/api/public/'+url.split('/')[-1]).json()
    assert public['read_only'] is True
    assert not {'participants','latitude','longitude','messages','leader_id','plate','guest_key'} & public.keys()
    assert 'Private Nachricht' not in str(public)
    assert owner.delete(root+'/share').status_code==200
    assert owner.get('/api/public/'+url.split('/')[-1]).status_code==404


def test_csrf_and_invalid_bearer_do_not_fall_back_to_cookie(owner):
    assert owner.post('/api/keys',json={'label':'Test'},headers={'origin':'https://evil.example'}).status_code==403
    assert owner.post('/api/keys',json={'label':'Test'},headers={'origin':'https://evil.example','authorization':'Bearer invalid'}).status_code==401
    assert owner.get('/api/admin').status_code==401
    assert owner.get('/openapi.json').status_code in (404,503)


def test_api_keys_scoped_to_owner_and_revoked(owner):
    created=trip(owner)
    issued=owner.post('/api/keys',json={'label':'Telemetrie'}).json()
    headers={'authorization':'Bearer '+issued['token']}
    assert owner.post('/api/trips/'+created['id']+'/samples',headers=headers,json={'odometer_km':1000,'energy_used_kwh':200}).status_code==200
    stranger=new_driver('Fremder')
    their_trip=trip(stranger)
    assert owner.get('/api/trips/'+their_trip['id'],headers=headers).status_code==404
    assert owner.delete('/api/keys/'+issued['id']).status_code==200
    assert owner.get('/api/me',headers=headers).status_code==401


def test_oauth_state_is_bound_and_single_use(owner,monkeypatch):
    monkeypatch.setattr(settings,'tesla_client_id','test-client')
    monkeypatch.setattr(settings,'tesla_client_secret','test-secret')
    result=owner.get('/auth/tesla',follow_redirects=False)
    assert result.status_code==307
    from urllib.parse import parse_qs,urlparse
    query=parse_qs(urlparse(result.headers['location']).query)
    assert 'vehicle_location' in query['scope'][0]
    assert query['code_challenge_method']==['S256']
    state=query['state'][0]
    stranger=new_driver('Fremder')
    assert stranger.get('/auth/tesla/callback',params={'state':state,'code':'wrong'}).status_code==400
    assert owner.get('/auth/tesla/callback',params={'state':state},follow_redirects=False).status_code==307
    assert owner.get('/auth/tesla/callback',params={'state':state}).status_code==400


def test_raw_tokens_not_returned_and_credentials_encrypted(owner):
    from app.fleet import save_token
    uid=owner.get('/api/me').json()['id']
    save_token(uid,{'access_token':'sensitive-token','refresh_token':'refresh-secret','expires_in':100})
    stored=db.one('SELECT * FROM credentials WHERE user_id=?',(uid,))['encrypted_token']
    assert 'sensitive-token' not in stored
    assert b'sensitive-token' in cipher().decrypt(stored.encode())
    assert 'sensitive-token' not in owner.get('/api/me').text
    assert 'refresh-secret' not in owner.get('/api/vehicles').text


def test_pin_attempts_limited(owner):
    trip(owner)
    for _ in range(5):
        assert owner.post('/api/trips/join',json={'pin':'000000'}).status_code in (200,404)
    assert owner.post('/api/trips/join',json={'pin':'000000'}).status_code==429


def test_chat_can_be_reloaded_and_paginated_after_trip_end(owner):
    created=trip(owner)
    root='/api/trips/'+created['id']
    first=owner.post(root+'/messages',json={'text':'Erste Nachricht'}).json()
    second=owner.post(root+'/messages',json={'text':'Zweite Nachricht'}).json()
    loaded=owner.get(root+'/messages')
    assert loaded.status_code==200
    assert [row['id'] for row in loaded.json()]==[first['id'],second['id']]
    assert [row['id'] for row in owner.get(root+'/messages',params={'before':second['created_at']}).json()]==[first['id']]
    owner.post(root+'/finish')
    assert len(owner.get(root+'/messages').json())==2


def test_voice_grants_microphone_only_and_end_bounded(owner,monkeypatch):
    created=trip(owner)
    monkeypatch.setattr(settings,'livekit_key','test-key')
    monkeypatch.setattr(settings,'livekit_secret','b'*40)
    async def ready(trip_id):
        return True
    monkeypatch.setattr('app.main.ensure_voice_room',ready)
    result=owner.post('/api/trips/'+created['id']+'/voice-token').json()
    claims=jwt.decode(result['token'],settings.livekit_secret,algorithms=['HS256'])
    assert claims['exp']<=created['ends_at']
    assert claims['video']['canPublishSources']==['microphone']
    assert claims['video']['room']=='trip-'+created['id']
