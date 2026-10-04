import time
import pytest
from app import db
from .test_access import trip, passenger
from .conftest import new_driver


def test_personal_and_vehicle_positions_stay_independent(owner):
    created = trip(owner)
    root = '/api/trips/' + created['id']
    uid = owner.get('/api/me').json()['id']
    key = owner.post('/api/keys', json={'label':'Vehicle input', 'days':None}).json()
    headers = {'authorization':'Bearer ' + key['token']}
    assert owner.post(root+'/samples', headers=headers, json={'source':'telemetry', 'latitude':51, 'longitude':9, 'battery_pct':72}).status_code == 200
    # Browser clients cannot use this endpoint to overwrite any vehicle metric.
    assert owner.post(root+'/samples', json={'source':'browser', 'latitude':50, 'longitude':8, 'battery_pct':1, 'odometer_km':999}).status_code == 200
    member = next(row for row in owner.get(root).json()['participants_detail'] if row['id'] == uid)
    assert member['data']['latitude'] == 51
    assert member['data']['longitude'] == 9
    assert member['data']['battery_pct'] == 72
    assert member['personal_location']['latitude'] == 50
    latest = db.one("SELECT * FROM samples WHERE trip_id=? AND source='browser' ORDER BY id DESC", (created['id'],))
    assert latest['battery_pct'] is None and latest['odometer_km'] is None
    assert owner.post(root+'/samples', headers=headers, json={'source':'telemetry','battery_pct':70}).status_code == 200
    member = owner.get(root).json()['participants_detail'][0]
    assert member['data']['latitude'] == 51 and member['data']['battery_pct'] == 70
    assert member['personal_location']['latitude'] == 50
    assert owner.delete(root+'/location').status_code == 200
    member = owner.get(root).json()['participants_detail'][0]
    assert member['personal_location'] is None and member['data']['latitude'] == 51
    assert len(owner.get(root+'/history').json()) == 3


def test_passenger_location_is_trip_scoped_and_not_vehicle_telemetry(owner):
    created = trip(owner)
    root = '/api/trips/' + created['id']
    guest, _, _ = passenger(owner, created)
    uid = guest.get('/api/me').json()['id']
    assert guest.post(root+'/samples', json={'source':'browser','latitude':49.88,'longitude':8.66}).status_code == 200
    member = next(row for row in owner.get(root).json()['participants_detail'] if row['id'] == uid)
    assert member['personal_location']['latitude'] == 49.88
    assert member['data'] == {} and member['vehicle_id'] is None
    assert guest.post(root+'/samples', json={'source':'telemetry','latitude':50,'longitude':8}).status_code == 403
    assert guest.post(root+'/samples', json={'source':'browser'}).status_code == 422
    other = trip(new_driver('Other convoy'))
    assert guest.post('/api/trips/'+other['id']+'/samples', json={'source':'browser','latitude':50,'longitude':8}).status_code == 404
    assert guest.delete('/api/trips/'+other['id']+'/location').status_code == 404
    assert owner.get(root+'/ranking').json() == []
    assert guest.delete(root+'/location').status_code == 200
    assert owner.post(root+'/finish').status_code == 200
    assert guest.post(root+'/samples', json={'source':'browser','latitude':50,'longitude':8}).status_code == 403


def test_stale_person_locations_disappear_without_erasing_history(owner):
    created = trip(owner)
    root = '/api/trips/' + created['id']
    owner.post(root+'/samples', json={'source':'browser','latitude':50,'longitude':8})
    db.execute('UPDATE personal_locations SET updated_at=? WHERE trip_id=?', (time.time()-301,created['id']))
    assert owner.get(root).json()['participants_detail'][0]['personal_location'] is None
    assert len(owner.get(root+'/history').json()) == 1


def test_non_expiring_key_outlasts_timed_key_and_remains_revocable(owner, monkeypatch):
    created = trip(owner)
    unlimited = owner.post('/api/keys', json={'label':'Permanent integration','days':None}).json()
    timed = owner.post('/api/keys', json={'label':'One day','days':1}).json()
    assert unlimited['expires_at'] is None
    listed = owner.get('/api/keys').json()
    assert next(key for key in listed if key['id'] == unlimited['id'])['expires_at'] is None
    assert timed['expires_at'] > time.time()
    future = time.time() + 400*86400
    monkeypatch.setattr('app.security.time.time', lambda: future)
    permanent_headers = {'authorization':'Bearer '+unlimited['token']}
    assert owner.get('/api/me',headers=permanent_headers).status_code == 200
    assert owner.get('/api/me',headers={'authorization':'Bearer '+timed['token']}).status_code == 401
    # Key lifetime never bypasses the convoy's own time window.
    assert owner.post('/api/trips/'+created['id']+'/samples',headers=permanent_headers,json={'source':'browser','latitude':50,'longitude':8}).status_code == 403
    assert owner.delete('/api/keys/'+unlimited['id'],headers=permanent_headers).status_code == 200
    assert owner.get('/api/me',headers=permanent_headers).status_code == 401


@pytest.mark.parametrize('days', [0, -1, 366])
def test_invalid_fixed_key_lifetimes_rejected(owner, days):
    assert owner.post('/api/keys',json={'label':'Invalid', 'days':days}).status_code == 422
