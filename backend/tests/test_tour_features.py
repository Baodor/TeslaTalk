import asyncio
import json
import time
from fastapi.testclient import TestClient
from app import db, main
from app.main import app
from app.realtime import hub
from .conftest import new_driver
from .test_access import trip, passenger


def member(client,root):
    uid=client.get('/api/me').json()['id']
    return next(row for row in client.get(root).json()['participants_detail'] if row['id']==uid)


def test_browser_car_position_is_separate_from_personal_gps_and_real_metrics(owner):
    ride=trip(owner);root='/api/trips/'+ride['id']
    key=owner.post('/api/keys',json={'label':'Counters','days':None}).json()['token']
    assert owner.post(root+'/samples',headers={'authorization':'Bearer '+key},json={'source':'telemetry','latitude':51,'longitude':9,'battery_pct':72,'energy_used_kwh':100}).status_code==200
    assert member(owner,root)['data']['latitude'] is None  # no paid-data fallback
    assert owner.post(root+'/samples',json={'source':'browser_vehicle','latitude':50,'longitude':8,'battery_pct':1,'energy_used_kwh':999,'device_id':'phone'}).status_code==200
    assert owner.post(root+'/samples',json={'source':'browser','latitude':49,'longitude':7}).status_code==200
    row=member(owner,root)
    assert row['data']['latitude']==50 and row['data']['battery_pct']==72
    assert row['data']['position_source']=='browser' and row['personal_location']['latitude']==49
    sample=db.one("SELECT * FROM samples WHERE source='browser_vehicle'")
    assert sample['battery_pct'] is None and sample['energy_used_kwh'] is None
    assert owner.post(root+'/samples',headers={'authorization':'Bearer '+key},json={'source':'telemetry','energy_used_kwh':101}).status_code==200
    assert member(owner,root)['data']['battery_pct']==72  # retain real metrics across GPS updates
    assert owner.delete(root+'/location?source=browser_vehicle&device_id=phone').status_code==200
    assert member(owner,root)['data']['latitude'] is None
    assert member(owner,root)['personal_location']['latitude']==49


def test_old_gps_and_other_browser_cleanup_cannot_replace_or_remove_newer_position(owner):
    ride=trip(owner);root='/api/trips/'+ride['id'];now=time.time()
    for lat,device,captured in [(50,'phone',now),(51,'tesla-browser',now-10)]:
        assert owner.post(root+'/samples',json={'source':'browser_vehicle','latitude':lat,'longitude':8,'device_id':device,'captured_at':captured}).status_code==200
    assert member(owner,root)['data']['latitude']==50
    assert owner.delete(root+'/location?source=browser_vehicle&device_id=tesla-browser').status_code==200
    assert member(owner,root)['data']['latitude']==50
    for captured in [now-61,now+60]:
        assert owner.post(root+'/samples',json={'source':'browser_vehicle','latitude':52,'longitude':8,'captured_at':captured}).status_code==422
    db.execute('UPDATE browser_vehicle_locations SET updated_at=?',(now-301,))
    assert member(owner,root)['data']['latitude'] is None


def test_passengers_bearers_and_other_trips_cannot_supply_car_position(owner):
    ride=trip(owner);root='/api/trips/'+ride['id'];guest,_,_=passenger(owner,ride)
    body={'source':'browser_vehicle','latitude':50,'longitude':8}
    assert guest.post(root+'/samples',json=body).status_code==403
    other=new_driver('Different trip GPS')
    assert other.post(root+'/samples',json=body).status_code==404
    key=owner.post('/api/keys',json={'label':'GPS key','days':None}).json()['token']
    assert owner.post(root+'/samples',headers={'authorization':'Bearer '+key},json=body).status_code==403
    assert not db.one('SELECT * FROM browser_vehicle_locations')


def test_changing_car_hides_the_previous_car_browser_fix(owner):
    ride=trip(owner);root='/api/trips/'+ride['id'];uid=owner.get('/api/me').json()['id']
    assert owner.post(root+'/samples',json={'source':'browser_vehicle','latitude':50,'longitude':8}).status_code==200
    db.execute('INSERT INTO vehicles(id,user_id,name,model) VALUES (?,?,?,?)',('second-car',uid,'Other car','Model Y'))
    assert owner.post('/api/vehicles/second-car/select').status_code==200
    assert member(owner,root)['data']['latitude'] is None


def test_viewer_traffic_and_browser_gps_do_not_trigger_paid_vehicle_reads(owner,monkeypatch):
    ride=trip(owner);root='/api/trips/'+ride['id'];reads=[]
    async def paid(*args):reads.append(args);raise AssertionError('Unexpected paid polling')
    async def broadcast(*args):pass
    monkeypatch.setattr(main.fleet,'fetch_vehicle',paid)
    monkeypatch.setattr(main.fleet,'fetch_navigation',paid)
    monkeypatch.setattr(hub,'broadcast',broadcast)
    assert owner.post(root+'/samples',json={'source':'browser_vehicle','latitude':50,'longitude':8}).status_code==200
    link=owner.post(root+'/spectator-link').json()['url'].split('/')[-1]
    visitor=TestClient(app)
    for _ in range(3):assert visitor.get('/api/spectator/'+link).status_code==200
    hub.rooms[ride['id']]={object():owner.get('/api/me').json()['id']}
    next_poll=asyncio.run(main.background_cycle(0))
    assert next_poll>=time.time()+main.settings.navigation_poll_interval-1
    assert reads==[]
    hub.rooms.clear()


def test_spectator_link_is_read_only_private_rotatable_and_ends_with_trip(owner):
    ride=trip(owner);root='/api/trips/'+ride['id'];guest,_,_=passenger(owner,ride)
    uid=owner.get('/api/me').json()['id'];vin=owner.get('/api/vehicles').json()[0]['id']
    assert owner.post(root+'/samples',json={'source':'browser_vehicle','latitude':50,'longitude':8}).status_code==200
    assert guest.post(root+'/samples',json={'source':'browser','latitude':49,'longitude':7}).status_code==200
    assert owner.post(root+'/messages',json={'text':'private chat must not leak'}).status_code==200
    assert guest.post(root+'/spectator-link').status_code==403
    token=owner.post(root+'/spectator-link').json()['url'].split('/')[-1]
    visitor=TestClient(app,headers={'origin':'http://testserver'})
    response=visitor.get('/api/spectator/'+token);data=response.json()
    assert response.headers['cache-control']=='no-store'
    assert data['read_only'] and len(data['participants'])==1
    assert data['participants'][0]['data']['latitude']==50
    encoded=json.dumps(data)
    assert all(value not in encoded for value in [uid,vin,'private chat must not leak','personal_location','avatar_url','plate'])
    assert visitor.post(root+'/toilet').status_code==401
    assert visitor.get(root+'/messages').status_code==401
    next_token=owner.post(root+'/spectator-link').json()['url'].split('/')[-1]
    assert visitor.get('/api/spectator/'+token).status_code==404
    assert visitor.get('/api/spectator/'+next_token).status_code==200
    assert owner.delete(root+'/spectator-link').status_code==200
    assert visitor.get('/api/spectator/'+next_token).status_code==404
    final_token=owner.post(root+'/spectator-link').json()['url'].split('/')[-1]
    assert owner.post(root+'/finish').status_code==200
    assert visitor.get('/api/spectator/'+final_token).status_code==404


def test_planned_spectator_link_exposes_no_positions_before_start(owner):
    ride=trip(owner);root='/api/trips/'+ride['id']
    token=owner.post(root+'/spectator-link').json()['url'].split('/')[-1]
    db.execute('UPDATE trips SET starts_at=? WHERE id=?',(time.time()+60,ride['id']))
    response=TestClient(app).get('/api/spectator/'+token).json()
    assert response['status']=='planned' and response['participants']==[]


def test_toilet_requests_and_confirmation_are_deduplicated_and_only_leader_can_confirm(owner,monkeypatch):
    ride=trip(owner);root='/api/trips/'+ride['id'];guest,_,_=passenger(owner,ride)
    leader_id=owner.get('/api/me').json()['id'];guest_id=guest.get('/api/me').json()['id']
    events=[];pushes=[]
    async def broadcast(trip_id,event):events.append(event)
    monkeypatch.setattr(hub,'broadcast',broadcast)
    monkeypatch.setattr(main.push,'enqueue',lambda *args,**kwargs:pushes.append((args,kwargs)))
    first=guest.post(root+'/toilet').json();again=guest.post(root+'/toilet').json()
    assert first==again and len(first['pause_requests'])==1
    assert len(events)==1 and events[0]['alert']['recipient_id']==leader_id
    assert pushes[0][0][0]==leader_id and len(pushes)==1
    ids=[row['id'] for row in first['pause_requests']]
    assert guest.post(root+'/toilet/confirm',json={'request_ids':ids}).status_code==403
    result=owner.post(root+'/toilet/confirm',json={'request_ids':ids}).json()
    assert result['pause_requests']==[] and result['message']['kind']=='toilet_departure'
    assert any(event.get('sound') is True for event in events)
    assert {args[0] for args,kw in pushes if kw.get('message_key')=='toilet_departure'}=={leader_id,guest_id}
    events_before=len(events);pushes_before=len(pushes)
    assert owner.post(root+'/toilet/confirm',json={'request_ids':ids}).json()['message'] is None
    assert len(events)==events_before and len(pushes)==pushes_before
    messages=owner.get(root+'/messages').json()
    assert len(messages)==1 and messages[0]['kind']=='toilet_departure'


def test_expired_or_foreign_members_cannot_send_pause_alerts(owner):
    ride=trip(owner);root='/api/trips/'+ride['id'];other=new_driver('Wrong trip pause')
    assert other.post(root+'/toilet').status_code==404
    assert owner.post(root+'/finish').status_code==200
    assert owner.post(root+'/toilet').status_code==403


def test_navigation_poll_still_reads_only_consented_cars_with_a_planner_and_private_viewer(owner,monkeypatch):
    ride=trip(owner);root='/api/trips/'+ride['id']
    friend=new_driver('Navigation poll friend');friend.post('/api/trips/join',json={'pin':ride['pin']})
    leader=owner.get('/api/me').json()
    assert owner.post(root+'/route/adopt/'+leader['id']).status_code==200
    reads=[]
    async def navigation(user_id,vehicle):
        reads.append((user_id,vehicle['id']));return main.fleet.demo_navigation()
    async def update(*args):pass
    monkeypatch.setattr(main.fleet,'fetch_navigation',navigation)
    monkeypatch.setattr(main,'update_shared_navigation',update)
    hub.rooms[ride['id']]={object():leader['id']}
    try:
        next_poll=asyncio.run(main.background_cycle(0))
        assert reads==[(leader['id'],leader['favorite_vehicle'])]
        asyncio.run(main.background_cycle(next_poll))
        assert len(reads)==1
        hub.rooms.clear();asyncio.run(main.background_cycle(0));assert len(reads)==1
        assert owner.post(root+'/finish').status_code==200
        hub.rooms[ride['id']]={object():leader['id']}
        asyncio.run(main.background_cycle(0));assert len(reads)==1
    finally:hub.rooms.clear()
