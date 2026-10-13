import json,time,uuid
import pytest
from app import abrp,db,fleet
from app.config import settings
from app.security import cipher
from .test_access import trip,passenger
from .conftest import new_driver

TYPE='tesla:test:variant'

@pytest.fixture
def configured(owner,monkeypatch):
    abrp.cache.clear();abrp.locks.clear()
    monkeypatch.setattr(settings,'abrp_api_key','isolated-planning-key')
    monkeypatch.setattr(settings,'abrp_daily_limit',20)
    calls=[]
    async def provider(method,path,body=None,params=None,session=None):
        calls.append((method,path,body,session))
        if path=='/auth/login':return {'access_token':'private-abrp-session','expires_in':300,'refresh_token':'not-stored'}
        if path=='/network':return {'items':[{'id':85,'name':'IONITY'},{'id':86,'name':'EnBW'}],'meta':{'hasNextPage':False,'endCursor':''}}
        if path=='/vehicle/_list':return {'vehicles':[{'typecode':TYPE,'title':'Exact test variant','manufacturer':'Tesla','model':'Model 3'}]}
        if path=='/charger/_google-place-ids':return {'chargerToGoogle':{'42':'ChIJ_Real_Reference'}}
        if path=='/charger/42':return {'id':42,'network':{'id':85,'name':'IONITY'}}
        if path=='/plan':return route()
        if path.endswith('/request'):return {'planId':'saved','typecode':TYPE,'request':{'destinations':[{'location':{'type':'ADDRESS','value':'Darmstadt'}},{'location':{'type':'CHARGER_ID','value':42},'name':'IONITY charger'},{'location':{'type':'ADDRESS','value':'Hamburg'}}],'vehicle':{'currentSocFrac':.7},'charging':{'networkPreferences':[{'id':85,'preference':'EXCLUSIVE'}]}}}
        raise AssertionError(path)
    monkeypatch.setattr(abrp,'request',provider)
    yield owner,calls
    abrp.cache.clear();abrp.locks.clear()


def route():
    def origin(name,lat,lon,**extra):return {'name':name,'type':'DESTINATION','lat':lat,'long':lon,'arrivalSocFrac':.3,'departureSocFrac':.8,'chargeDurationSec':0,**extra}
    return {'planId':'provider-id','routes':[{'summary':{'distanceM':500000,'durationSec':20000},'legs':[
        {'origin':origin('Darmstadt',49.87,8.65),'driveDetails':{}},
        {'origin':origin('IONITY station',51,9,charger={'id':42},chargeDurationSec=1200),'driveDetails':{}},
        {'origin':origin('Hamburg',53.55,10),'driveDetails':{}}
    ]}]}


def calculate_body(owner,**changes):
    return {'request_id':str(uuid.uuid4()),'planner_user_id':owner.get('/api/me').json()['id'],'typecode':TYPE,'departure_soc':70,'arrival_soc':10,'network_ids':[85,86],'exclusive':True,'destinations':[{'value':'Darmstadt'},{'value':'Kassel','stay_minutes':20},{'value':'Hamburg'}],'costs_confirmed':True,**changes}


def test_account_connection_is_encrypted_browser_only_and_password_never_stored(configured):
    owner,calls=configured
    assert owner.post('/api/me/abrp',json={'username':'Benny','password':'private-password'}).status_code==200
    status=owner.get('/api/me/abrp').json();assert status['connected'] and status['username']=='Benny'
    stored=db.one('SELECT * FROM abrp_accounts')
    assert 'private-abrp-session' not in stored['encrypted_session']
    plain=cipher().decrypt(stored['encrypted_session'].encode()).decode()
    assert 'private-abrp-session' in plain and 'private-password' not in plain and 'not-stored' not in plain
    token=owner.post('/api/keys',json={'label':'test','days':None}).json()['token']
    assert owner.post('/api/me/abrp',headers={'authorization':'Bearer '+token},json={'username':'Benny','password':'ignored'}).status_code==403
    assert len(calls)==1
    assert owner.delete('/api/me/abrp').json()['connected'] is False


def test_plan_uses_selected_vehicle_soc_exclusive_networks_and_stays_preview(configured,monkeypatch):
    owner,calls=configured;ride=trip(owner);root='/api/trips/'+ride['id'];sent=[]
    async def command(*args,**kwargs):sent.append(args)
    monkeypatch.setattr(fleet,'send_navigation',command)
    body=calculate_body(owner)
    response=owner.post(root+'/abrp/plan',json=body)
    assert response.status_code==200,response.text
    wire=next(call[2] for call in calls if call[1]=='/plan')
    assert wire['vehicle']=={'identifier':{'type':'TYPECODE','value':TYPE},'currentSocFrac':.7}
    assert wire['charging']['networkPreferences']==[{'id':85,'preference':'EXCLUSIVE'},{'id':86,'preference':'EXCLUSIVE'}]
    assert wire['destinations'][1]['timeSettings']['stayForSeconds']==1200
    plan=response.json()['plan'];assert plan['stops'][0]['charger_id']==42
    assert plan['stops'][0]['google_place_id']=='ChIJ_Real_Reference' and plan['stops'][0]['operator']=='IONITY'
    assert plan['stops'][0]['charge_minutes']==20 and plan['stops'][0]['arrival_soc']==30
    assert plan['distance_km']==500 and plan['source']=='abrp' and len(plan['stops'])==2
    assert not db.one('SELECT * FROM charging_plans') and sent==[]
    assert owner.post(root+'/abrp/plan',json=body).json()==response.json()
    assert sum(path=='/plan' for _,path,_,_ in calls)==1
    assert owner.put(root+'/charging-plan',json=plan).status_code==200
    assert sent==[]
    assert owner.post(root+'/charging-plan/send',json={'request_id':str(uuid.uuid4()),'version':owner.get(root).json()['charging_plan']['version'],'stop_index':0}).status_code==200
    assert 'query_place_id=ChIJ_Real_Reference' in sent[0][2]


def test_link_import_only_fetches_original_parameters_and_requires_own_account(configured):
    owner,calls=configured;ride=trip(owner);path='/api/trips/'+ride['id']+'/abrp/link';url='https://abetterrouteplanner.com/?plan_uuid='+str(uuid.uuid4())
    assert owner.post(path,json={'url':url}).status_code==409
    owner.post('/api/me/abrp',json={'username':'Benny','password':'not-stored'})
    response=owner.post(path,json={'url':url});assert response.status_code==200,response.text
    assert response.json()['kind']=='parameters_only'
    assert response.json()['destinations'][1]['charger_id']==42
    assert response.json()['exclusive'] and response.json()['network_ids']==[85]
    assert not any(path=='/plan' for _,path,_,_ in calls)
    assert owner.post(path,json={'url':'https://evil.example/?plan_uuid='+str(uuid.uuid4())}).status_code==422
    assert len([call for call in calls if call[1].endswith('/request')])==1


def test_foreign_members_passengers_finished_trips_and_unconfirmed_costs_cannot_plan(configured):
    owner,calls=configured;ride=trip(owner);root='/api/trips/'+ride['id'];guest,_,_=passenger(owner,ride)
    friend=new_driver('ABRP friend');friend.post('/api/trips/join',json={'pin':ride['pin']})
    body=calculate_body(owner)
    assert guest.post(root+'/abrp/plan',json=body).status_code==403
    assert friend.post(root+'/abrp/plan',json=body).status_code==403
    assert owner.post(root+'/abrp/plan',json=body|{'costs_confirmed':False}).status_code==422
    assert owner.post(root+'/abrp/plan',json=body|{'planner_user_id':'foreign-user'}).status_code==404
    assert owner.post(root+'/finish').status_code==200
    assert owner.post(root+'/abrp/plan',json=body).status_code==403
    assert calls==[]


def test_daily_limit_and_request_id_block_duplicate_charged_requests(configured,monkeypatch):
    owner,calls=configured;ride=trip(owner);root='/api/trips/'+ride['id'];monkeypatch.setattr(settings,'abrp_daily_limit',1)
    body=calculate_body(owner)
    assert owner.post(root+'/abrp/plan',json=body).status_code==200
    assert owner.post(root+'/abrp/plan',json=body|{'departure_soc':60}).status_code==409
    assert owner.post(root+'/abrp/plan',json=body|{'request_id':str(uuid.uuid4())}).status_code==429
    assert sum(path=='/plan' for _,path,_,_ in calls)==1


def test_uncertain_provider_result_is_read_only_and_not_recalculated(configured,monkeypatch):
    from fastapi import HTTPException
    owner,calls=configured;ride=trip(owner);root='/api/trips/'+ride['id'];original=abrp.request
    async def fail(method,path,*args,**kwargs):
        if path=='/plan':calls.append((method,path,None,None));raise HTTPException(502,'Unconfirmed')
        return await original(method,path,*args,**kwargs)
    monkeypatch.setattr(abrp,'request',fail)
    body=calculate_body(owner)
    assert owner.post(root+'/abrp/plan',json=body).status_code==502
    assert owner.post(root+'/abrp/plan',json=body).json()['status']=='unknown'
    assert owner.get(root+'/abrp/requests/'+body['request_id']).json()['status']=='unknown'
    assert sum(path=='/plan' for _,path,_,_ in calls)==1


def test_optional_station_metadata_failure_keeps_paid_route_without_false_reference(configured,monkeypatch):
    from fastapi import HTTPException
    owner,calls=configured;ride=trip(owner);original=abrp.request
    async def partial(method,path,*args,**kwargs):
        if path.startswith('/charger/'):raise HTTPException(503,'No metadata')
        return await original(method,path,*args,**kwargs)
    monkeypatch.setattr(abrp,'request',partial)
    response=owner.post('/api/trips/'+ride['id']+'/abrp/plan',json=calculate_body(owner))
    assert response.status_code==200,response.text
    assert response.json()['plan']['stops'][0]['google_place_id'] is None


def test_provider_line_precision_five_and_six_are_decoded_without_inventing_geometry():
    assert abrp.points({'precision':5,'value':'_p~iF~ps|U_ulLnnqC_mqNvxq'+chr(96)+'@'})==[(38.5,-120.2),(40.7,-120.95),(43.252,-126.453)]
    with pytest.raises(ValueError):abrp.points({'precision':4,'value':'invalid'})


def test_http_adapter_uses_only_fixed_tls_origin_and_header_keys(configured,monkeypatch):
    import asyncio,httpx
    owner,calls=configured;original_client=httpx.AsyncClient;seen=[]
    def provider(req):seen.append(req);return httpx.Response(200,json={'items':[]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original_client(transport=httpx.MockTransport(provider),**kwargs))
    # Exercise the real adapter, not the catalogue/provider fixture.
    import importlib
    source=__import__('runpy').run_path(abrp.__file__,run_name='app._abrp_transport')
    result=asyncio.run(source['request']('GET','/network',session='own-session'))
    assert result=={'items':[]}
    assert str(seen[0].url)=='https://api.iternio.com/2/network'
    assert seen[0].headers['x-api-key']=='isolated-planning-key' and seen[0].headers['x-abrp-session']=='own-session'
    assert 'isolated-planning-key' not in str(seen[0].url)


def test_provider_result_after_trip_end_cannot_be_shared_or_saved(configured,monkeypatch):
    owner,calls=configured;ride=trip(owner);original=abrp.request
    async def end(method,path,*args,**kwargs):
        result=await original(method,path,*args,**kwargs)
        if path=='/plan':db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),ride['id']))
        return result
    monkeypatch.setattr(abrp,'request',end)
    assert owner.post('/api/trips/'+ride['id']+'/abrp/plan',json=calculate_body(owner)).status_code==403
    assert not db.one('SELECT * FROM charging_plans')


def test_expired_account_does_not_expose_old_tokens_or_read_saved_plan(configured):
    owner,calls=configured;ride=trip(owner)
    owner.post('/api/me/abrp',json={'username':'Benny','password':'not-stored'})
    db.execute('UPDATE abrp_accounts SET expires_at=0')
    assert owner.get('/api/me/abrp').json()['connected'] is False
    assert owner.post('/api/trips/'+ride['id']+'/abrp/link',json={'url':'https://abetterrouteplanner.com/?plan_uuid='+str(uuid.uuid4())}).status_code==409
    assert len(calls)==1


def test_invalid_account_password_is_never_echoed_in_validation_errors(configured):
    owner,calls=configured
    secret='private-password-'+('x'*1000)
    response=owner.post('/api/me/abrp',json={'username':'Benny','password':secret})
    assert response.status_code==422
    assert 'private-password' not in response.text and 'input' not in response.text
    assert not calls


def test_malformed_saved_parameters_are_rejected_without_charged_planning(configured,monkeypatch):
    owner,calls=configured;ride=trip(owner)
    owner.post('/api/me/abrp',json={'username':'Benny','password':'not-stored'})
    original=abrp.request
    async def malformed(method,path,*args,**kwargs):
        if path.endswith('/request'):return {'request':{'destinations':[{'location':{'type':'COORDINATES'}}]}}
        return await original(method,path,*args,**kwargs)
    monkeypatch.setattr(abrp,'request',malformed)
    response=owner.post('/api/trips/'+ride['id']+'/abrp/link',json={'url':'https://abetterrouteplanner.com/?plan_uuid='+str(uuid.uuid4())})
    assert response.status_code==502
    assert not any(path=='/plan' for _,path,_,_ in calls)


def test_malformed_optional_station_metadata_does_not_lose_the_paid_plan(configured,monkeypatch):
    owner,calls=configured;ride=trip(owner);original=abrp.request
    async def malformed(method,path,*args,**kwargs):
        if path=='/charger/_google-place-ids':return {'chargerToGoogle':[]}
        if path=='/charger/42':return {'id':42,'network':'invalid'}
        return await original(method,path,*args,**kwargs)
    monkeypatch.setattr(abrp,'request',malformed)
    response=owner.post('/api/trips/'+ride['id']+'/abrp/plan',json=calculate_body(owner))
    assert response.status_code==200,response.text
    assert response.json()['plan']['stops'][0]['google_place_id'] is None
    assert sum(path=='/plan' for _,path,_,_ in calls)==1
