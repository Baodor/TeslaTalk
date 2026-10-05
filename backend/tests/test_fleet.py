import pytest
from fastapi import HTTPException
from app import db, fleet


def test_vehicle_sync_accepts_null_configuration_without_guessing_a_model(owner,monkeypatch):
    uid=owner.get('/api/me').json()['id']
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(uid,))
    async def request(user_id,path,params=None):
        return [{'vin':'LRWYGCEK1PC000001','display_name':'Unser Auto','vehicle_config':None}]
    monkeypatch.setattr(fleet,'request',request)
    result=owner.post('/api/vehicles/sync')
    assert result.status_code==200,result.text
    vehicle=next(row for row in result.json() if row['id']=='LRWYGCEK1PC000001')
    assert vehicle['model']=='Tesla'
    # Once detailed data provides a model, a basic list refresh must retain it.
    db.execute("UPDATE vehicles SET model='Model Y' WHERE id=?",(vehicle['id'],))
    assert owner.post('/api/vehicles/sync').status_code==200
    assert db.one('SELECT model FROM vehicles WHERE id=?',(vehicle['id'],))['model']=='Model Y'


def test_vehicle_refresh_formats_the_actual_model(owner,monkeypatch):
    uid=owner.get('/api/me').json()['id']
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(uid,))
    vehicle={'id':'LRWYGCEK1PC000001','user_id':uid,'name':'Unser Auto','model':'Tesla','data':'{}'}
    db.execute('INSERT INTO vehicles VALUES (?,?,?,?,?)',tuple(vehicle.values()))
    async def request(user_id,path,params=None):
        return {'drive_state':{'speed':10},'vehicle_config':{'car_type':'modely'}}
    monkeypatch.setattr(fleet,'request',request)
    response=owner.post('/api/vehicles/'+vehicle['id']+'/refresh')
    assert response.status_code==200,response.text
    assert response.json()['speed_kmh']==16.1
    assert db.one('SELECT model FROM vehicles WHERE id=?',(vehicle['id'],))['model']=='Model Y'


@pytest.mark.parametrize('payload',[
    None, [], {'drive_state':['not an object']}, {'drive_state':{'speed':'invalid'}},
    {'drive_state':{'latitude':float('nan')}},
])
def test_malformed_vehicle_data_becomes_a_controlled_upstream_error(payload):
    with pytest.raises(HTTPException) as error:
        fleet.normalize(payload)
    assert error.value.status_code==502
