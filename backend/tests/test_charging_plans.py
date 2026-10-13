import json
import time
import uuid
import pytest
from app import db, fleet, charging_plans
from .conftest import new_driver
from .test_access import trip, passenger

GPX='''<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1"><rte><name>ABRP test plan</name>
<rtept lat="49.47" lon="8.60"><name>Ladenburg</name></rtept>
<rtept lat="50.10" lon="8.70"><name>IONITY Teststation</name><type>charging</type><extensions><google_place_id>ChIJ_Test_Station</google_place_id><operator>IONITY</operator></extensions></rtept>
<rtept lat="53.55" lon="10.00"><name>Hamburg</name></rtept></rte></gpx>'''


def plan(owner):
    ride=trip(owner);root='/api/trips/'+ride['id']
    preview=owner.post(root+'/charging-plan/preview',json={'filename':'abrp.gpx','content':GPX})
    assert preview.status_code==200,preview.text
    saved=owner.put(root+'/charging-plan',json=preview.json())
    assert saved.status_code==200,saved.text
    return ride,root,saved.json()


def test_gpx_preview_retains_stop_order_reference_and_never_sends_commands(owner,monkeypatch):
    sent=[]
    async def send(*args,**kwargs):sent.append(args)
    monkeypatch.setattr(fleet,'send_navigation',send)
    ride,root,saved=plan(owner)
    assert [stop['name'] for stop in saved['stops']]==['Ladenburg','IONITY Teststation','Hamburg']
    assert [stop['kind'] for stop in saved['stops']]==['waypoint','charging','destination']
    assert saved['stops'][1]['google_place_id']=='ChIJ_Test_Station'
    assert saved['current_stop'] is None and saved['confirmations']==[] and sent==[]
    exported=owner.get(root+'/charging-plan/export')
    assert exported.status_code==200
    assert set(exported.json())=={'format','version','title','stops'}
    imported=owner.post(root+'/charging-plan/preview',json={'filename':'saved.json','content':exported.text})
    assert imported.json()=={'title':saved['title'],'stops':saved['stops']}


@pytest.mark.parametrize('content',[
    '<!DOCTYPE gpx [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><gpx><wpt lat="50" lon="8"><name>&xxe;</name></wpt></gpx>',
    '<gpx><trk><trkseg><trkpt lat="50" lon="8"/></trkseg></trk></gpx>',
    '<gpx><rte><rtept lat="50" lon="8"/></rte></gpx>',
    '<gpx><wpt lat="nan" lon="8"><name>Invalid</name></wpt></gpx>',
    '<gpx><rte><rtept lat="50" lon="8"><name>A</name></rtept></rte><rte><rtept lat="51" lon="9"><name>B</name></rtept></rte></gpx>',
])
def test_invalid_or_track_only_exports_are_rejected_without_guessing_stops(owner,content):
    ride=trip(owner)
    assert owner.post('/api/trips/'+ride['id']+'/charging-plan/preview',json={'filename':'bad.gpx','content':content}).status_code==422
    assert not db.one('SELECT * FROM charging_plans')


def test_only_leader_can_save_plan_and_guest_cannot_send_or_confirm_stops(owner):
    ride,root,saved=plan(owner);guest,_,_=passenger(owner,ride)
    friend=new_driver('Charging friend permissions');friend.post('/api/trips/join',json={'pin':ride['pin']})
    body={'title':saved['title'],'stops':saved['stops']}
    assert guest.put(root+'/charging-plan',json=body).status_code==403
    assert friend.put(root+'/charging-plan',json=body).status_code==403
    command={'request_id':str(uuid.uuid4()),'version':saved['version'],'stop_index':1}
    assert guest.post(root+'/charging-plan/send',json=command).status_code==403
    assert friend.post(root+'/charging-plan/send',json=command).status_code==403
    assert guest.post(root+'/charging-plan/confirm',json={'version':saved['version'],'stop_index':1,'recognized':True}).status_code==403


def test_group_stop_transfer_requires_each_car_consent_and_is_idempotent(owner,monkeypatch):
    ride,root,saved=plan(owner);friend=new_driver('Charging consenting friend')
    friend.post('/api/trips/join',json={'pin':ride['pin']});sent=[]
    async def send(user_id,vehicle,destination,trip_id,**kwargs):
        if kwargs.get('guard'):kwargs['guard']()
        sent.append((user_id,destination));return {'accepted':True,'demo':True}
    monkeypatch.setattr(fleet,'send_navigation',send)
    command={'request_id':str(uuid.uuid4()),'version':saved['version'],'stop_index':1}
    first=owner.post(root+'/charging-plan/send',json=command)
    assert first.status_code==200,first.text
    assert len(sent)==1 and len(first.json()['vehicles'])==1
    assert 'IONITY Teststation' in sent[0][1] and 'query_place_id=ChIJ_Test_Station' in sent[0][1]
    assert owner.post(root+'/charging-plan/send',json=command).json()==first.json()
    assert len(sent)==1
    assert owner.post(root+'/charging-plan/send',json=command|{'stop_index':2}).status_code==409
    assert friend.post(root+'/route/accept').status_code==200
    assert len(sent)==2 and sent[1][0]==friend.get('/api/me').json()['id']
    # GPS/route refresh must not replace the charger POI with a bare coordinate.
    assert 'query_place_id=ChIJ_Test_Station' in sent[1][1]
    before=len(sent)
    assert owner.get(root+'/charging-plan/requests/'+command['request_id']).json()==first.json()
    assert len(sent)==before


def test_station_and_preconditioning_are_never_confirmed_from_http_acceptance(owner,monkeypatch):
    ride,root,saved=plan(owner)
    async def send(*args,**kwargs):return {'accepted':True,'demo':True}
    monkeypatch.setattr(fleet,'send_navigation',send)
    assert owner.post(root+'/charging-plan/send',json={'request_id':str(uuid.uuid4()),'version':saved['version'],'stop_index':1}).status_code==200
    assert owner.get(root).json()['charging_plan']['confirmations']==[]
    confirmation={'version':saved['version'],'stop_index':1,'recognized':False,'preconditioning':True}
    assert owner.post(root+'/charging-plan/confirm',json=confirmation).status_code==422
    assert owner.post(root+'/charging-plan/confirm',json=confirmation|{'recognized':True}).status_code==200
    assert owner.get(root).json()['charging_plan']['confirmations'][0]['preconditioning']==1
    uid=owner.get('/api/me').json()['id']
    db.execute('INSERT INTO vehicles(id,user_id,name,model) VALUES (?,?,?,?)',('replacement-car',uid,'Replacement','Model Y'))
    assert owner.post('/api/vehicles/replacement-car/select').status_code==200
    assert owner.get(root).json()['charging_plan']['confirmations']==[]


def test_plan_version_change_rejects_old_commands_and_resets_confirmation(owner):
    ride,root,saved=plan(owner)
    replacement=owner.put(root+'/charging-plan',json={'title':'New plan','stops':saved['stops']}).json()
    assert replacement['version']!=saved['version'] and replacement['current_stop'] is None
    assert owner.post(root+'/charging-plan/send',json={'request_id':str(uuid.uuid4()),'version':saved['version'],'stop_index':1}).status_code==409
    assert owner.post(root+'/charging-plan/confirm',json={'version':saved['version'],'stop_index':1,'recognized':True}).status_code==409


def test_unconfirmed_navigation_is_not_retried_after_a_connection_failure(owner,monkeypatch):
    import httpx
    ride,root,saved=plan(owner);sent=[]
    async def send(*args,**kwargs):sent.append(args);raise httpx.ReadTimeout('No reply')
    monkeypatch.setattr(fleet,'send_navigation',send)
    command={'request_id':str(uuid.uuid4()),'version':saved['version'],'stop_index':1}
    first=owner.post(root+'/charging-plan/send',json=command).json()
    assert first['vehicles'][0]['status']=='unknown'
    assert owner.post(root+'/charging-plan/send',json=command).json()==first
    assert owner.post(root+'/charging-plan/send',json=command|{'request_id':str(uuid.uuid4())}).status_code==200
    assert len(sent)==1


def test_trip_ending_mid_batch_stops_further_vehicle_commands(owner,monkeypatch):
    ride,root,saved=plan(owner);friend=new_driver('Ending mid charging transfer')
    friend.post('/api/trips/join',json={'pin':ride['pin']});friend.post(root+'/route/accept')
    sent=[]
    async def send(*args,**kwargs):
        sent.append(args);db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),ride['id']));return {'accepted':True,'demo':True}
    monkeypatch.setattr(fleet,'send_navigation',send)
    command={'request_id':str(uuid.uuid4()),'version':saved['version'],'stop_index':1}
    assert owner.post(root+'/charging-plan/send',json=command).status_code==403
    assert len(sent)==1
    assert owner.post(root+'/charging-plan/send',json=command).status_code==403
    assert len(sent)==1
