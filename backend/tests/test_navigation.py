import asyncio
import base64
import json
import time
from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from app import db, fleet
from app.navigation import NavigationTelemetry, decode_route_line, from_fleet
from .conftest import new_driver


def route_line(points):
    previous = (0,0)
    output = ''
    for point in points:
        current = tuple(round(value*1_000_000) for value in point)
        for value, old in zip(current,previous):
            delta = value-old
            encoded = ~(delta << 1) if delta < 0 else delta << 1
            while encoded >= 32:
                output += chr((32 | (encoded & 31))+63)
                encoded >>= 5
            output += chr(encoded+63)
        previous = current
    return base64.b64encode(output.encode()).decode()


POINTS = [(49.8728,8.6512),(49.8729,8.6389),(49.8728,8.6289)]


def trip(client, title='Navigation trip'):
    now = datetime.now(timezone.utc)
    response = client.post('/api/trips',json={'title':title,'starts_at':(now-timedelta(minutes=1)).isoformat(),'ends_at':(now+timedelta(hours=1)).isoformat()})
    assert response.status_code == 200,response.text
    return response.json()


def choose_source(client,ride):
    uid=client.get('/api/me').json()['id']
    response=client.post(f'/api/trips/{ride["id"]}/route/adopt/{uid}')
    assert response.status_code==200,response.text
    return response.json()


def key(client):
    return client.post('/api/keys',json={'label':'Route import','days':1}).json()['token']


def telemetry(**overrides):
    return {'active':True,'destination':'Darmstadt Hauptbahnhof','destination_latitude':49.8728,'destination_longitude':8.6289,
            'distance_remaining_km':2.1,'minutes_remaining':6,'battery_arrival_pct':76,'traffic_delay_minutes':0,
            'route_line':route_line(POINTS),'captured_at':time.time(),**overrides}


def test_fleet_navigation_normalizes_units_and_preserves_zeroes():
    result = from_fleet({'active_route_destination':' Station ','active_route_latitude':0,'active_route_longitude':8,
                         'active_route_miles_to_arrival':10,'active_route_minutes_to_arrival':0,
                         'active_route_energy_at_arrival':0,'active_route_traffic_minutes_delay':0})
    assert result['status'] == 'active'
    assert result['destination'] == 'Station'
    assert result['destination_latitude'] == 0
    assert result['distance_remaining_km'] == 16.1
    assert result['battery_arrival_pct'] == result['minutes_remaining'] == result['traffic_delay_minutes'] == 0
    assert result['arrival_at'] == result['updated_at']
    assert result['route_points'] == []  # no fabricated connecting line


@pytest.mark.parametrize('milliseconds',[False,True])
def test_navigation_keeps_vehicle_measurement_time_and_uses_it_for_arrival(milliseconds):
    captured = time.time()-90
    navigation = from_fleet({'timestamp':captured*1000 if milliseconds else captured,
                             'active_route_destination':'Already calculated route','active_route_minutes_to_arrival':10})
    assert navigation['updated_at'] == pytest.approx(captured)
    assert navigation['arrival_at'] == pytest.approx(captured+600)


@pytest.mark.parametrize('drive,status',[
    ({},'unavailable'), ({'speed':10},'unavailable'),
    ({'active_route_destination':None,'active_route_latitude':None},'inactive'),
    ({'active_route_destination':'','active_route_miles_to_arrival':0},'inactive'),
    ({'active_route_destination':'Ziel','active_route_latitude':90.1,'active_route_longitude':8},'active'),
])
def test_missing_cancelled_and_partial_fleet_navigation(drive,status):
    result = from_fleet(drive)
    assert result['status'] == status
    assert result['destination_latitude'] is None
    assert result['route_points'] == []


def test_route_line_decodes_precision_six_and_negative_deltas():
    assert decode_route_line(route_line(POINTS)) == POINTS
    assert decode_route_line(route_line([(-33.123456,151.654321),(-33.124456,151.653321)])) == [(-33.123456,151.654321),(-33.124456,151.653321)]


@pytest.mark.parametrize('value',['not base64','',base64.b64encode(b'_').decode(),base64.b64encode(b'??').decode(),base64.b64encode(b'!???').decode(),base64.b64encode(b'~~~~~~~~~~~~~~~').decode(),route_line([(91,8),(92,9)])])
def test_invalid_and_unbounded_route_lines_rejected(value):
    with pytest.raises(ValueError):
        decode_route_line(value)


def test_route_line_point_limit():
    with pytest.raises(ValueError,match='20.000'):
        decode_route_line(route_line([(0,0)]*20_001))


@pytest.mark.parametrize('changes',[
    {'destination_longitude':None}, {'destination_latitude':float('nan')}, {'battery_arrival_pct':101},
    {'minutes_remaining':-1}, {'route_line':'broken'}, {'captured_at':0}, {'captured_at':time.time()+3600},
    {'active':False}, {'arbitrary':'unexpected'}, {'destination':None,'destination_latitude':None,'destination_longitude':None},
])
def test_telemetry_validation(changes):
    with pytest.raises(ValidationError):
        NavigationTelemetry(**telemetry(**changes))


def test_route_is_automatic_only_after_initial_planning_vehicle_selection(owner):
    leader = owner.get('/api/me').json()
    vehicle_id = leader['favorite_vehicle']
    ride = trip(owner)
    outsider = new_driver('Route outsider')
    member = new_driver('Route friend')
    assert member.post('/api/trips/join',json={'pin':ride['pin']}).status_code == 200
    assert owner.post(f'/api/vehicles/{vehicle_id}/navigation/refresh').json()['source'] == 'demo'
    assert owner.get(f'/api/trips/{ride["id"]}').json()['navigation'] is None
    assert outsider.post(f'/api/vehicles/{vehicle_id}/navigation/refresh').status_code == 404
    assert member.post(f'/api/trips/{ride["id"]}/navigation').status_code == 403
    choose_source(owner,ride)
    assert member.get(f'/api/trips/{ride["id"]}').json()['navigation']['destination'] == 'Demo: Darmstadt Hauptbahnhof'
    assert outsider.get(f'/api/trips/{ride["id"]}').status_code == 404
    assert owner.delete(f'/api/trips/{ride["id"]}/navigation').status_code == 405
    assert member.post(f'/api/trips/{ride["id"]}/route/adopt/{leader["id"]}').status_code == 403


def test_navigation_import_requires_owner_bearer_and_rejects_old_snapshots(owner):
    vehicle_id = owner.get('/api/me').json()['favorite_vehicle']
    path = f'/api/vehicles/{vehicle_id}/navigation'
    body = telemetry()
    assert owner.put(path,json=body).status_code == 403
    outsider = new_driver('Route second owner')
    assert outsider.put(path,json=body,headers={'authorization':'Bearer '+key(outsider)}).status_code == 404
    headers = {'authorization':'Bearer '+key(owner)}
    result = owner.put(path,json=body,headers=headers)
    assert result.status_code == 200,result.text
    assert result.json()['route_points'] == [list(point) for point in POINTS]
    assert owner.put(path,json=body,headers=headers).status_code == 409
    assert owner.post(path+'/refresh').json()['route_points'] == [list(point) for point in POINTS]
    assert owner.put(path,json=telemetry(route_line='invalid'),headers=headers).status_code == 422


def test_selected_telemetry_navigation_updates_and_cancel_automatically(owner):
    vehicle_id = owner.get('/api/me').json()['favorite_vehicle']
    ride = trip(owner)
    path = f'/api/vehicles/{vehicle_id}/navigation'
    trip_path = f'/api/trips/{ride["id"]}'
    headers = {'authorization':'Bearer '+key(owner)}
    assert owner.put(path,json=telemetry(),headers=headers).status_code == 200
    choose_source(owner,ride)
    result = owner.put(path,json=telemetry(destination='Neues Ziel'),headers=headers)
    assert result.status_code == 200,result.text
    assert owner.get(trip_path).json()['navigation']['destination'] == 'Neues Ziel'
    assert owner.put(path,json={'active':False,'captured_at':time.time()},headers=headers).status_code == 200
    cancelled = owner.get(trip_path).json()['navigation']
    assert cancelled['status'] == 'inactive' and cancelled['route_points'] == [] and cancelled['destination'] is None
    assert owner.put(path,json=telemetry(),headers=headers).status_code == 200
    assert owner.get(trip_path).json()['navigation']['status'] == 'active'


def test_cancelled_selected_route_is_broadcast_to_members_immediately(owner,monkeypatch):
    from app.realtime import hub
    ride = trip(owner)
    choose_source(owner,ride)
    events=[]
    async def broadcast(trip_id,event):
        events.append((trip_id,event))
    monkeypatch.setattr(hub,'broadcast',broadcast)
    vehicle_id=owner.get('/api/me').json()['favorite_vehicle']
    headers={'authorization':'Bearer '+key(owner)}
    result=owner.put(f'/api/vehicles/{vehicle_id}/navigation',json={'active':False,'captured_at':time.time()},headers=headers)
    assert result.status_code==200,result.text
    navigation_events=[event for tid,event in events if tid==ride['id'] and event['type']=='navigation']
    assert len(navigation_events)==1
    assert navigation_events[0]['navigation']['status']=='inactive'
    assert navigation_events[0]['navigation']['destination'] is None


def test_navigation_waiting_for_trip_lock_cannot_overwrite_finished_archive(owner):
    from app import route_planning
    ride=trip(owner)
    choose_source(owner,ride)
    me=owner.get('/api/me').json()
    previous=db.one('SELECT data FROM trip_navigation WHERE trip_id=?',(ride['id'],))['data']
    async def race():
        gate=route_planning.lock(ride['id'])
        await gate.acquire()
        update=asyncio.create_task(route_planning.observe(me['favorite_vehicle'],me['id'],from_fleet({'active_route_destination':'Too late'})))
        await asyncio.sleep(0)  # observe has found the trip, but awaits its lock
        db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),ride['id']))
        gate.release()
        await update
    asyncio.run(race())
    assert db.one('SELECT data FROM trip_navigation WHERE trip_id=?',(ride['id'],))['data']==previous


def test_finished_navigation_stays_archived_and_is_not_public(owner):
    vehicle_id = owner.get('/api/me').json()['favorite_vehicle']
    ride = trip(owner)
    path = f'/api/trips/{ride["id"]}'
    choose_source(owner,ride)
    snapshot = owner.get(path).json()['navigation']
    assert owner.post(path+'/finish').status_code == 200
    assert owner.post(path+'/navigation').status_code == 403
    headers = {'authorization':'Bearer '+key(owner)}
    assert owner.put(f'/api/vehicles/{vehicle_id}/navigation',json=telemetry(),headers=headers).status_code == 200
    assert owner.get(path).json()['navigation'] == snapshot
    share = owner.post(path+'/share').json()['url']
    public = owner.get('/api/public/'+share.split('/')[-1]).json()
    assert 'navigation' not in public and 'route_points' not in public
    db.execute('INSERT INTO vehicles VALUES (?,?,?,?,?)',('another-car',ride['leader_id'],'Another','Tesla','{}'))
    assert owner.post('/api/vehicles/another-car/select').status_code == 200
    assert owner.get(path).json()['navigation'] == snapshot


def test_changing_vehicle_stops_active_sharing(owner):
    ride = trip(owner)
    path = f'/api/trips/{ride["id"]}'
    choose_source(owner,ride)
    db.execute('INSERT INTO vehicles VALUES (?,?,?,?,?)',('new-car',ride['leader_id'],'New car','Tesla','{}'))
    assert owner.post('/api/vehicles/new-car/select').status_code == 200
    assert owner.get(path).json()['navigation'] is None


def test_trip_ending_during_upstream_fetch_cannot_enable_sharing(owner,monkeypatch):
    ride = trip(owner)
    choose_source(owner,ride)
    previous=db.one('SELECT data FROM trip_navigation WHERE trip_id=?',(ride['id'],))['data']
    async def fetch(user_id,vehicle):
        db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),ride['id']))
        return from_fleet({'active_route_destination':'Ziel'})
    monkeypatch.setattr(fleet,'fetch_navigation',fetch)
    assert owner.post(f'/api/trips/{ride["id"]}/navigation').status_code == 403
    assert db.one('SELECT data FROM trip_navigation WHERE trip_id=?',(ride['id'],))['data'] == previous


def test_shared_refresh_limit(owner):
    vehicle_id = owner.get('/api/me').json()['favorite_vehicle']
    ride = trip(owner)
    choose_source(owner,ride)
    assert owner.post(f'/api/trips/{ride["id"]}/navigation').status_code == 200
    for _ in range(4):
        assert owner.post(f'/api/vehicles/{vehicle_id}/navigation/refresh').status_code == 200
    assert owner.post(f'/api/vehicles/{vehicle_id}/refresh').status_code == 429


def test_concurrent_vehicle_fetches_share_cache_without_waking(owner,monkeypatch):
    user = owner.get('/api/me').json()
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(user['id'],))
    vehicle = db.one('SELECT * FROM vehicles WHERE id=?',(user['favorite_vehicle'],))
    calls = []
    async def request(user_id,path,params=None):
        calls.append((path,params))
        await asyncio.sleep(0.01)
        return {'drive_state':{'active_route_destination':'Station','active_route_miles_to_arrival':10}}
    monkeypatch.setattr(fleet,'request',request)
    async def fetch():
        return await asyncio.gather(fleet.fetch_vehicle(user['id'],vehicle),fleet.fetch_vehicle(user['id'],vehicle))
    first, second = asyncio.run(fetch())
    assert first == second and len(calls) == 1
    assert calls[0][0].endswith('/vehicle_data') and 'location_data' in calls[0][1]['endpoints']
    assert first['navigation']['distance_remaining_km'] == 16.1


def test_recent_telemetry_survives_vehicle_poll_and_expires(owner,monkeypatch):
    user = owner.get('/api/me').json()
    vehicle_id = user['favorite_vehicle']
    headers = {'authorization':'Bearer '+key(owner)}
    assert owner.put(f'/api/vehicles/{vehicle_id}/navigation',json=telemetry(),headers=headers).status_code == 200
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(user['id'],))
    async def request(user_id,path,params=None):
        return {'drive_state':{'active_route_destination':'Fleet target'}}
    monkeypatch.setattr(fleet,'request',request)
    fresh = owner.post(f'/api/vehicles/{vehicle_id}/refresh')
    assert fresh.status_code == 200,fresh.text
    assert fresh.json()['navigation']['source'] == 'telemetry'
    data = json.loads(db.one('SELECT data FROM vehicles WHERE id=?',(vehicle_id,))['data'])
    data['navigation']['updated_at'] -= 121
    data['fleet_fetched_at'] = 0
    db.execute('UPDATE vehicles SET data=? WHERE id=?',(json.dumps(data),vehicle_id))
    assert owner.post(f'/api/vehicles/{vehicle_id}/navigation/refresh').json()['destination'] == 'Fleet target'
