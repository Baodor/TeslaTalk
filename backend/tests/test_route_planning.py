import json
import time
import pytest
import httpx
from app import db, fleet, route_planning
from app.config import settings
from app.navigation import from_fleet
from .conftest import new_driver
from .test_navigation import trip, key, telemetry, POINTS


def group(owner):
    ride=trip(owner)
    friend=new_driver('Planning friend')
    assert friend.post('/api/trips/join',json={'pin':ride['pin']}).status_code==200
    return ride,friend,friend.get('/api/me').json()


def test_group_starts_without_a_leader_route_and_recommends_two_different_cars(owner):
    ride,friend,other=group(owner)
    leader=owner.get('/api/me').json()
    for user,battery,remaining in ((leader,20,180),(other,40,150)):
        row=db.one('SELECT data FROM vehicles WHERE id=?',(user['favorite_vehicle'],))
        data=json.loads(row['data']) | {'battery_pct':battery,'range_km':remaining,'updated_at':time.time()}
        db.execute('UPDATE vehicles SET data=? WHERE id=?',(json.dumps(data),user['favorite_vehicle']))
    result=owner.get(f'/api/trips/{ride["id"]}').json()
    assert result['navigation'] is None
    assert result['route_overview']['planner_user_id'] is None
    assert result['route_overview']['recommendations']=={'lowest_battery_user_id':leader['id'],'lowest_range_user_id':other['id']}
    assert result['route_overview']['charging_stops_confirmed'] is False
    # Missing range is not treated as zero and stale values never win.
    data=json.loads(db.one('SELECT data FROM vehicles WHERE id=?',(other['favorite_vehicle'],))['data'])
    data.update(range_km=None,updated_at=time.time()-301)
    db.execute('UPDATE vehicles SET data=? WHERE id=?',(json.dumps(data),other['favorite_vehicle']))
    assert owner.get(f'/api/trips/{ride["id"]}').json()['route_overview']['recommendations']['lowest_range_user_id']==leader['id']


def test_selected_other_car_plans_first_and_only_consenting_cars_get_the_target(owner,monkeypatch):
    ride,friend,other=group(owner)
    leader=owner.get('/api/me').json()
    path=f'/api/trips/{ride["id"]}'
    outsider=new_driver('Planning non-follower')
    assert outsider.post('/api/trips/join',json={'pin':ride['pin']}).status_code==200
    assert owner.post(path+'/route/plan',json={'planner_user_id':other['id'],'destination':'Initial destination'}).status_code==403
    assert friend.post(path+'/route/accept').status_code==200
    calls=[]
    async def send(user_id,vehicle,destination,trip_id):
        fleet.navigation_command_access(trip_id,user_id,vehicle['id'])
        calls.append((user_id,vehicle['id'],destination))
        data=json.loads(vehicle['data'])
        data['navigation']=from_fleet({'active_route_destination':'Calculated by selected Tesla','active_route_latitude':50,'active_route_longitude':8})
        db.execute('UPDATE vehicles SET data=? WHERE id=?',(json.dumps(data),vehicle['id']))
        return {'accepted':True,'demo':False}
    monkeypatch.setattr(fleet,'send_navigation',send)
    response=owner.post(path+'/route/plan',json={'planner_user_id':other['id'],'destination':'Initial destination'})
    assert response.status_code==200,response.text
    assert calls[0]==(other['id'],other['favorite_vehicle'],'Initial destination')
    assert calls[1]==(leader['id'],leader['favorite_vehicle'],'50.000000, 8.000000')
    assert len(calls)==2  # no consent, no command to third participant
    detail=owner.get(path).json()
    assert detail['route_overview']['planner_user_id']==other['id']
    assert detail['navigation']['destination']=='Calculated by selected Tesla'
    assert detail['route_overview']['transfer_mode']=='destination_only'
    assert friend.post(path+'/route/plan',json={'planner_user_id':other['id'],'destination':'Unauthorized'}).status_code==403


def test_withdrawing_consent_stops_future_transfers_and_changes_source_when_selected(owner):
    ride,friend,other=group(owner)
    path=f'/api/trips/{ride["id"]}'
    assert friend.post(path+'/route/accept').status_code==200
    assert owner.post(path+'/route/plan',json={'planner_user_id':other['id'],'destination':'Station'}).status_code==200
    assert owner.get(path).json()['navigation'] is not None
    assert friend.delete(path+'/route/accept').status_code==200
    result=owner.get(path).json()
    assert result['navigation'] is None and result['route_overview']['planner_user_id'] is None
    assert not db.one('SELECT user_id FROM route_followers WHERE trip_id=? AND user_id=?',(ride['id'],other['id']))


def test_accepted_command_does_not_publish_a_route_measured_before_the_command(owner,monkeypatch):
    ride,friend,other=group(owner)
    path=f'/api/trips/{ride["id"]}'
    assert friend.post(path+'/route/accept').status_code==200
    calls=[]
    async def send(user_id,vehicle,destination,trip_id):
        calls.append(user_id)
        data=json.loads(vehicle['data'])
        data['navigation']=from_fleet({'timestamp':(time.time()-30)*1000,'active_route_destination':'Old destination'})
        db.execute('UPDATE vehicles SET data=? WHERE id=?',(json.dumps(data),vehicle['id']))
        return {'accepted':True,'demo':False}
    monkeypatch.setattr(fleet,'send_navigation',send)
    response=owner.post(path+'/route/plan',json={'planner_user_id':other['id'],'destination':'New destination'})
    assert response.status_code==200,response.text
    assert response.json()['command_accepted'] is True
    assert response.json()['navigation'] is None
    assert owner.get(path).json()['navigation'] is None
    assert calls==[other['id']]  # old route must not trigger group commands


def test_adoption_rechecks_selected_vehicle_after_the_vehicle_fetch(owner,monkeypatch):
    ride,friend,other=group(owner)
    path=f'/api/trips/{ride["id"]}'
    assert friend.post(path+'/route/accept').status_code==200
    async def fetch(user_id,vehicle):
        db.execute('INSERT INTO vehicles VALUES (?,?,?,?,?)',('replacement',user_id,'Replacement','Tesla','{}'))
        db.execute('UPDATE members SET vehicle_id=? WHERE trip_id=? AND user_id=?',('replacement',ride['id'],user_id))
        return from_fleet({'active_route_destination':'Route from the old car'})
    monkeypatch.setattr(fleet,'fetch_navigation',fetch)
    response=owner.post(path+'/route/adopt/'+other['id'])
    assert response.status_code==409,response.text
    assert owner.get(path).json()['navigation'] is None
    assert not db.one('SELECT user_id FROM trip_planners WHERE trip_id=?',(ride['id'],))


def test_problem_only_after_acceptance_and_push_deduplicates(owner,monkeypatch):
    ride,friend,other=group(owner)
    path=f'/api/trips/{ride["id"]}'
    assert friend.post(path+'/route/problem',json={'reason':'cannot_follow'}).status_code==409
    assert friend.post(path+'/route/accept').status_code==200
    queued=[]
    monkeypatch.setattr(route_planning.push,'enqueue',lambda *args:queued.append(args))
    for _ in range(2):
        assert friend.post(path+'/route/problem',json={'reason':'cannot_follow'}).status_code==200
    row=db.one('SELECT * FROM route_followers WHERE trip_id=? AND user_id=?',(ride['id'],other['id']))
    assert row['problem']==row['notified_problem']=='cannot_follow'
    assert len(queued)==1 and queued[0][0]==ride['leader_id']
    assert 'Station' not in queued[0][1] and '8.6289' not in queued[0][1]
    headers={'authorization':'Bearer '+key(friend)}
    assert friend.put(f'/api/vehicles/{other["favorite_vehicle"]}/navigation',json=telemetry(),headers=headers).status_code==200
    adopted=owner.post(path+'/route/adopt/'+other['id'])
    assert adopted.status_code==200,adopted.text
    assert adopted.json()['route_overview']['planner_user_id']==other['id']


def test_target_acceptance_is_not_full_route_or_charging_confirmation():
    reference=from_fleet({'active_route_destination':'A','active_route_latitude':50,'active_route_longitude':8})
    actual=reference.copy()
    assert route_planning.compare(reference,actual,None)==('unconfirmed',None)
    actual=actual | {'destination_longitude':9}
    assert route_planning.compare(reference,actual,None)==('different','different_route')
    actual=reference | {'battery_arrival_pct':-5}
    assert route_planning.compare(reference,actual,None)==('different','insufficient_battery')
    actual=reference | {'updated_at':time.time()-301}
    assert route_planning.compare(reference,actual,None)==('unconfirmed',None)


def test_line_comparison_handles_sampling_different_roads_and_approaches():
    reference=from_fleet({'active_route_destination':'A'}) | {'route_points':POINTS}
    actual=reference | {'route_points':POINTS.copy()}
    assert route_planning.compare(reference,actual,None)==('matching',None)
    actual=reference | {'route_points':[POINTS[0],(49.874,8.645),(49.884,8.630),POINTS[-1]]}
    assert route_planning.compare(reference,actual,None)==('different','different_route')
    actual=reference | {'route_points':[(50,9),POINTS[-1]]}
    assert route_planning.compare(reference,actual,None)==('unconfirmed',None)


def test_live_navigation_command_is_limited_to_specific_rest_endpoint(owner,monkeypatch):
    ride=trip(owner)
    me=owner.get('/api/me').json()
    vehicle=db.one('SELECT * FROM vehicles WHERE id=?',(me['favorite_vehicle'],))
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(me['id'],))
    monkeypatch.setattr(settings,'navigation_commands',True)
    async def token(user_id):
        return 'isolated-test-only-token'
    monkeypatch.setattr(fleet,'token_for',token)
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={'response':{'result':True}})
    client_class=httpx.AsyncClient
    monkeypatch.setattr(fleet.httpx,'AsyncClient',lambda **kwargs:client_class(transport=httpx.MockTransport(respond),**kwargs))
    import asyncio
    result=asyncio.run(fleet.send_navigation(me['id'],vehicle,'Darmstadt Hauptbahnhof',ride['id']))
    assert result=={'accepted':True,'demo':False}
    assert len(requests)==1
    assert requests[0].method=='POST' and requests[0].url.path.endswith('/command/navigation_request')
    body=json.loads(requests[0].content)
    assert body['value']=={'android.intent.extra.TEXT':'Darmstadt Hauptbahnhof'}
    assert body['type']=='share_ext_content_raw'
    assert body['locale']=='de-DE'


def test_command_expiry_is_rechecked_after_token_refresh(owner,monkeypatch):
    ride=trip(owner)
    me=owner.get('/api/me').json()
    vehicle=db.one('SELECT * FROM vehicles WHERE id=?',(me['favorite_vehicle'],))
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(me['id'],))
    monkeypatch.setattr(settings,'navigation_commands',True)
    async def token(user_id):
        db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),ride['id']))
        return 'not-for-real-use'
    monkeypatch.setattr(fleet,'token_for',token)
    import asyncio
    with pytest.raises(Exception) as result:
        asyncio.run(fleet.send_navigation(me['id'],vehicle,'Station',ride['id']))
    assert result.value.status_code==403


def test_commands_are_disabled_until_configured_and_do_not_break_reading(owner,monkeypatch):
    ride=trip(owner)
    me=owner.get('/api/me').json()
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(me['id'],))
    monkeypatch.setattr(settings,'navigation_commands',False)
    result=owner.post(f'/api/trips/{ride["id"]}/route/plan',json={'planner_user_id':me['id'],'destination':'Station'})
    assert result.status_code==503 and 'vehicle_cmds' in result.json()['detail']
    assert owner.get(f'/api/trips/{ride["id"]}').json()['navigation'] is None


def test_oauth_only_requests_command_scope_when_enabled(client,monkeypatch):
    monkeypatch.setattr(settings,'tesla_client_id','client-id')
    monkeypatch.setattr(settings,'tesla_client_secret','client-secret')
    from urllib.parse import urlsplit,parse_qs
    for enabled in (False,True):
        monkeypatch.setattr(settings,'navigation_commands',enabled)
        response=client.get('/auth/tesla',follow_redirects=False)
        scopes=parse_qs(urlsplit(response.headers['location']).query)['scope'][0].split()
        assert ('vehicle_cmds' in scopes)==enabled
        assert 'vehicle_location' in scopes
