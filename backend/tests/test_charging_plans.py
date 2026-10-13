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


def test_csv_table_preview_uses_explicit_coordinates_and_preserves_charger_place_id(owner):
    ride=trip(owner);root='/api/trips/'+ride['id']
    csv='Wegpunkt;Breitengrad;Längengrad;Ladedauer;Link\nIONITY Teststation;50.1;8.7;00:20;https://www.google.com/maps/search/?api=1&query=50.1,8.7&query_place_id=ChIJ_Test\nHamburg;53.55;10;00:00;\n'
    response=owner.post(root+'/charging-plan/preview',json={'filename':'ABRP.csv','content':csv})
    assert response.status_code==200,response.text
    assert response.json()['stops'][0]['kind']=='charging'
    assert response.json()['stops'][0]['google_place_id']=='ChIJ_Test'
    assert response.json()['stops'][1]['kind']=='destination'
    assert not db.one('SELECT * FROM charging_plans')


def excel_file(*,linked=True,entity=False):
    import base64,io
    from zipfile import ZipFile
    data=io.BytesIO()
    with ZipFile(data,'w') as archive:
        archive.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ABRP" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml',('''<!DOCTYPE worksheet [<!ENTITY x "unsafe">]>''' if entity else '')+'''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Wegpunkt</t></is></c><c r="B1" t="inlineStr"><is><t>Ladedauer</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Test Supercharger</t></is></c><c r="B2"><v>20</v></c></row></sheetData><hyperlinks><hyperlink ref="A2" r:id="rId2"/></hyperlinks></worksheet>''')
        if linked:archive.writestr('xl/worksheets/_rels/sheet1.xml.rels','<Relationships><Relationship Id="rId2" Target="https://www.google.com/maps/search/?api=1&amp;query=50.1,8.7&amp;query_place_id=ChIJ_Excel_Test" TargetMode="External"/></Relationships>')
    return base64.b64encode(data.getvalue()).decode()


def test_excel_preview_reads_station_hyperlink_without_fetching_it(owner,monkeypatch):
    import httpx
    async def no_network(*args,**kwargs):raise AssertionError('Import fetched a link')
    monkeypatch.setattr(httpx.AsyncClient,'get',no_network)
    ride=trip(owner)
    response=owner.post('/api/trips/'+ride['id']+'/charging-plan/preview',json={'filename':'ABRP.xlsx','encoding':'base64','content':excel_file()})
    assert response.status_code==200,response.text
    stop=response.json()['stops'][0]
    assert stop['latitude']==50.1 and stop['longitude']==8.7 and stop['kind']=='charging'
    assert stop['google_place_id']=='ChIJ_Excel_Test'


@pytest.mark.parametrize('content',[excel_file(linked=False),excel_file(entity=True),'not-base64'])
def test_excel_without_coordinates_or_with_invalid_xml_is_rejected(owner,content):
    ride=trip(owner)
    assert owner.post('/api/trips/'+ride['id']+'/charging-plan/preview',json={'filename':'ABRP.xlsx','encoding':'base64','content':content}).status_code==422


def test_excel_archive_size_limit_is_checked_before_decompression(owner):
    import base64,io
    from zipfile import ZipFile,ZIP_DEFLATED
    data=io.BytesIO()
    with ZipFile(data,'w',compression=ZIP_DEFLATED) as archive:archive.writestr('xl/huge.xml',b'x'*2_000_001)
    ride=trip(owner)
    assert owner.post('/api/trips/'+ride['id']+'/charging-plan/preview',json={'filename':'bad.xlsx','encoding':'base64','content':base64.b64encode(data.getvalue()).decode()}).status_code==422
