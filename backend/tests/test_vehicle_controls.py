import json
import time
import uuid
import httpx
import pytest
from app import db, fleet, vehicle_controls
from app.config import settings
from .conftest import new_driver
from .test_navigation import trip, key
from .test_passenger_tesla import guest_trip


def group(owner):
    ride = trip(owner)
    friend = new_driver('Comfort friend')
    assert friend.post('/api/trips/join',json={'pin':ride['pin']}).status_code == 200
    return ride,friend,[owner.get('/api/me').json(),friend.get('/api/me').json()]


def batch(*users,action='climate_on',request_id=None):
    return {'request_id':request_id or str(uuid.uuid4()),'action':action,'vehicle_ids':[user['favorite_vehicle'] for user in users]}


def fake_cars(monkeypatch,users):
    monkeypatch.setattr(settings,'group_controls',True)
    monkeypatch.setattr(settings,'command_proxy_url','https://command-proxy.example.test:4443')
    monkeypatch.setattr(settings,'command_proxy_ca','')
    for user in users:
        db.execute("UPDATE users SET provider='tesla' WHERE id=?",(user['id'],))
    calls=[]
    async def data(user_id,path,params):
        return {'drive_state':{'shift_state':None,'speed':None,'timestamp':time.time()*1000},'vehicle_state':{'ft':0,'rt':0,'timestamp':time.time()*1000}}
    async def token(user_id):
        return 'test-token-'+user_id
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['verify'] is True
            assert kwargs['follow_redirects'] is False
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return None
        async def post(self,url,headers,json):
            calls.append((url,headers,json))
            return httpx.Response(200,json={'response':{'result':True}})
    monkeypatch.setattr(fleet,'request',data)
    monkeypatch.setattr(fleet,'token_for',token)
    monkeypatch.setattr(vehicle_controls.httpx,'AsyncClient',Client)
    return calls


def test_no_controls_without_separate_current_vehicle_consent(owner):
    ride,friend,users = group(owner)
    path = f'/api/trips/{ride["id"]}'
    assert friend.post(path+'/route/accept').status_code == 200
    assert owner.post(path+'/controls',json=batch(users[1])).status_code == 409
    detail = owner.get(path).json()['vehicle_controls']
    assert len(detail['vehicles']) == 2 and not any(car['allowed'] for car in detail['vehicles'])
    assert friend.post(path+'/controls/consent').status_code == 200
    command = owner.post(path+'/controls',json=batch(users[1]))
    assert command.status_code == 200 and command.json()['vehicles'][0]['status'] == 'demo'
    assert friend.post(path+'/controls',json=batch(users[1])).status_code == 403
    assert friend.get(path+'/controls/'+command.json()['request_id']).status_code == 403
    bearer = key(owner)
    for method,suffix,body in [('POST','/controls/consent',None),('POST','/controls',batch(users[1])),('GET','/controls/'+command.json()['request_id'],None)]:
        assert owner.request(method,path+suffix,headers={'authorization':'Bearer '+bearer},json=body).status_code == 403
    assert friend.delete(path+'/controls/consent').status_code == 200
    assert owner.post(path+'/controls',json=batch(users[1])).status_code == 409


def test_vehicle_change_revokes_consent_even_when_switching_back(owner):
    ride = trip(owner)
    user = owner.get('/api/me').json()
    path = f'/api/trips/{ride["id"]}'
    assert owner.post(path+'/controls/consent').status_code == 200
    db.execute('INSERT INTO vehicles VALUES (?,?,?,?,?)',('other-comfort-car',user['id'],'Other Tesla','Tesla','{}'))
    assert owner.post('/api/vehicles/other-comfort-car/select').status_code == 200
    assert owner.post('/api/vehicles/'+user['favorite_vehicle']+'/select').status_code == 200
    assert owner.post(path+'/controls',json=batch(user)).status_code == 409
    assert not db.one('SELECT * FROM control_grants WHERE user_id=?',(user['id'],))


def test_passenger_link_never_grants_comfort_control_or_includes_car(owner):
    guest,ride,_ = guest_trip(owner)
    uid=guest.get('/api/me').json()['id']
    # Simulate a legacy bad vehicle reference on a Tesla-linked passenger.
    car = owner.get('/api/me').json()['favorite_vehicle']
    db.execute('UPDATE members SET vehicle_id=? WHERE trip_id=? AND user_id=?',(car,ride['id'],uid))
    db.execute('INSERT INTO tesla_profile_links VALUES (?,?,?)',(uid,'linked-subject',time.time()))
    path = f'/api/trips/{ride["id"]}'
    assert guest.get(path).json()['vehicle_controls'] is None
    assert all(row['user_id'] != uid for row in owner.get(path).json()['vehicle_controls']['vehicles'])
    assert guest.post(path+'/controls/consent').status_code == 403
    assert guest.post(path+'/controls',json={'request_id':str(uuid.uuid4()),'action':'climate_on','vehicle_ids':[car]}).status_code == 403


@pytest.mark.parametrize('action,command,payload',[
    ('frunk_open','actuate_trunk',{'which_trunk':'front'}),
    ('rear_trunk_toggle','actuate_trunk',{'which_trunk':'rear'}),
    ('windows_vent','window_control',{'command':'vent'}),
    ('windows_close','window_control',{'command':'close'}),
    ('climate_on','auto_conditioning_start',{}),
    ('climate_off','auto_conditioning_stop',{}),
])
def test_only_allowed_exact_signed_proxy_commands_and_replay_never_resends(owner,monkeypatch,action,command,payload):
    ride=trip(owner);user=owner.get('/api/me').json();path=f'/api/trips/{ride["id"]}'
    calls=fake_cars(monkeypatch,[user])
    assert owner.post(path+'/controls/consent').status_code == 200
    body=batch(user,action=action)
    first=owner.post(path+'/controls',json=body)
    assert first.status_code == 200,first.text
    assert first.json()['vehicles'][0]['status'] == 'accepted'
    assert calls == [(settings.command_proxy_url+f'/api/1/vehicles/{user["favorite_vehicle"]}/command/{command}',{'Authorization':'Bearer test-token-'+user['id']},payload)]
    assert owner.post(path+'/controls',json=body).json() == first.json()
    assert owner.get(path+'/controls/'+body['request_id']).json() == first.json()
    assert len(calls) == 1
    assert owner.post(path+'/controls',json=body|{'action':'climate_off' if action!='climate_off' else 'climate_on'}).status_code == 409


@pytest.mark.parametrize('drive',[
    {'shift_state':'D','speed':20,'timestamp':time.time()*1000},
    {'shift_state':'N','speed':0,'timestamp':time.time()*1000},
    {'speed':0,'timestamp':time.time()*1000},
    {'shift_state':None,'timestamp':time.time()*1000},
    {'shift_state':'P','speed':0,'timestamp':(time.time()-60)*1000},
])
def test_trunks_and_windows_are_never_sent_without_fresh_park_confirmation(owner,monkeypatch,drive):
    ride=trip(owner);user=owner.get('/api/me').json();path=f'/api/trips/{ride["id"]}'
    calls=fake_cars(monkeypatch,[user])
    async def data(*args): return {'drive_state':drive,'vehicle_state':{'ft':0,'rt':0,'timestamp':time.time()*1000}}
    monkeypatch.setattr(fleet,'request',data)
    owner.post(path+'/controls/consent')
    for action in ['frunk_open','rear_trunk_toggle','windows_vent','windows_close']:
        result=owner.post(path+'/controls',json=batch(user,action=action))
        assert result.status_code == 200 and result.json()['vehicles'][0]['status'] == 'skipped'
    assert calls == []


@pytest.mark.parametrize('when',['fetch','token','leader_logout','trip_end','vehicle_change'])
def test_rights_rechecked_after_upstream_waits(owner,monkeypatch,when):
    ride=trip(owner);user=owner.get('/api/me').json();path=f'/api/trips/{ride["id"]}'
    calls=fake_cars(monkeypatch,[user]);owner.post(path+'/controls/consent')
    original=fleet.request
    async def data(*args):
        result=await original(*args)
        if when=='fetch': db.execute('DELETE FROM control_grants WHERE trip_id=?',(ride['id'],))
        if when=='leader_logout': db.execute("DELETE FROM sessions WHERE user_id=? AND kind='user'",(user['id'],))
        if when=='trip_end': db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),ride['id']))
        if when=='vehicle_change': db.execute('UPDATE members SET vehicle_id=NULL WHERE trip_id=?',(ride['id'],))
        return result
    async def token(*args):
        if when=='token': db.execute('DELETE FROM control_grants WHERE trip_id=?',(ride['id'],))
        return 'token'
    monkeypatch.setattr(fleet,'request',data);monkeypatch.setattr(fleet,'token_for',token)
    result=owner.post(path+'/controls',json=batch(user))
    assert result.status_code == 200 and result.json()['vehicles'][0]['status'] == 'error'
    assert calls == []


def test_group_failure_is_isolated_and_timeout_is_not_retried(owner,monkeypatch):
    ride,friend,users=group(owner);path=f'/api/trips/{ride["id"]}'
    calls=fake_cars(monkeypatch,users)
    owner.post(path+'/controls/consent');friend.post(path+'/controls/consent')
    real_client=vehicle_controls.httpx.AsyncClient
    class Client(real_client):
        async def post(self,url,headers,json):
            if users[0]['favorite_vehicle'] in url:
                calls.append((url,headers,json))
                raise httpx.ReadTimeout('test timeout')
            return await super().post(url,headers,json)
    monkeypatch.setattr(vehicle_controls.httpx,'AsyncClient',Client)
    body=batch(*users)
    result=owner.post(path+'/controls',json=body).json()
    assert [car['status'] for car in result['vehicles']] == ['unknown','accepted']
    assert len(calls) == 2
    assert owner.post(path+'/controls',json=body).json() == result
    assert len(calls) == 2


def test_invalid_actions_payloads_unconfigured_proxy_and_inactive_trip(owner,monkeypatch):
    ride=trip(owner);user=owner.get('/api/me').json();path=f'/api/trips/{ride["id"]}'
    for body in [batch(user,action='door_unlock'),batch(user)|{'command':'door_lock'},batch(user)|{'vehicle_ids':[]},batch(user)|{'vehicle_ids':[user['favorite_vehicle']]*2}]:
        assert owner.post(path+'/controls',json=body).status_code == 422
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(user['id'],))
    monkeypatch.setattr(settings,'group_controls',True)
    monkeypatch.setattr(settings,'command_proxy_url','http://proxy.example.test')
    assert owner.post(path+'/controls/consent').status_code == 503
    assert owner.post('/auth/tesla').status_code == 405
    owner.post(path+'/finish')
    assert owner.post(path+'/controls/consent').status_code == 403
    assert owner.post(path+'/controls',json=batch(user)).status_code == 403


def test_worker_recovery_never_replays_pending_commands(owner):
    ride=trip(owner);user=owner.get('/api/me').json();path=f'/api/trips/{ride["id"]}'
    owner.post(path+'/controls/consent');body=batch(user)
    payload=json.dumps({'action':body['action'],'vehicle_ids':body['vehicle_ids']},sort_keys=True)
    result={'request_id':body['request_id'],'action':body['action'],'status':'running','vehicles':[{'vehicle_id':user['favorite_vehicle'],'status':'pending'}]}
    db.execute('INSERT INTO control_batches VALUES (?,?,?,?,?,?,?)',(ride['id'],body['request_id'],user['id'],payload,json.dumps(result),'running',time.time()))
    assert owner.post(path+'/controls',json=batch(user)).status_code == 409
    vehicle_controls.recover_interrupted()
    recovered=owner.post(path+'/controls',json=body).json()
    assert recovered['status'] == 'completed' and recovered['vehicles'][0]['status'] == 'unknown'
