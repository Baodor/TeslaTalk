import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from app import db, main
from app.main import app
from app.security import pin_matches
from .test_navigation import trip


def anonymous():
    return TestClient(app,headers={'origin':'http://testserver'})


def invitation(owner,ride):
    return owner.get('/api/trips/'+ride['id']).json()['guest_url'].split('/')[-1]


def test_qr_registration_creates_own_name_and_pin_and_notifies_group(owner,monkeypatch):
    ride=trip(owner)
    key=invitation(owner,ride)
    guest=anonymous()
    events=[]
    async def broadcast(trip_id,event):
        events.append((trip_id,event))
    monkeypatch.setattr(main.hub,'broadcast',broadcast)
    before=time.time()
    result=guest.post(f'/api/guest/{key}/register',json={'name':' Anna ','pin':'012345'})
    assert result.status_code==200,result.text
    assert result.json()=={'trip_id':ride['id']}
    me=guest.get('/api/me').json()
    assert me['display_name']=='Anna' and me['provider']=='guest'
    assert me['needs_username'] is False
    passenger=db.one('SELECT * FROM passengers WHERE trip_id=?',(ride['id'],))
    assert passenger['user_id']==me['id'] and pin_matches('012345',passenger['pin_hash'])
    assert '012345' not in passenger['pin_hash']
    account=db.one('SELECT * FROM users WHERE id=?',(me['id'],))
    assert before<=account['last_login_at']<=time.time()
    assert len(events)==1 and events[0][0]==ride['id']
    member=next(person for person in events[0][1]['participants'] if person['id']==me['id'])
    assert member['role']=='passenger' and member['vehicle_id'] is None
    detail=owner.get('/api/trips/'+ride['id']).json()
    assert 'pin' not in detail['passengers'][0] and 'pin_hash' not in json.dumps(detail)
    assert guest.post('/api/trips/'+ride['id']+'/route/accept').status_code==403
    assert guest.get('/api/admin/users').status_code==401


def test_existing_guest_name_is_not_overwritten_and_own_pin_relogs_same_person(owner):
    ride=trip(owner)
    key=invitation(owner,ride)
    path=f'/api/guest/{key}'
    guest=anonymous()
    assert guest.post(path+'/register',json={'name':'Anna','pin':'012345'}).status_code==200
    me=guest.get('/api/me').json()
    old=db.one('SELECT * FROM passengers WHERE trip_id=?',(ride['id'],))
    stranger=anonymous()
    assert stranger.post(path+'/register',json={'name':' aNNa ','pin':'987654'}).status_code==409
    assert db.one('SELECT * FROM passengers WHERE trip_id=?',(ride['id'],))==old
    assert stranger.get('/api/me').status_code==401
    assert guest.post('/auth/logout').status_code==200
    assert guest.post(path+'/login',json={'name':'Anna','pin':'987654'}).status_code==401
    assert guest.post(path+'/login',json={'name':' ANNA ','pin':'012345'}).status_code==200
    assert guest.get('/api/me').json()['id']==me['id']
    assert len(db.all_rows("SELECT id FROM users WHERE provider='guest'"))==1
    assert guest.post('/api/trips/'+ride['id']+'/finish').status_code==403
    assert owner.post('/api/trips/'+ride['id']+'/finish').status_code==200
    assert guest.get('/api/trips/'+ride['id']).status_code in (401,403)
    assert guest.post(path+'/login',json={'name':'Anna','pin':'012345'}).status_code==403


@pytest.mark.parametrize('name,pin',[(' ','012345'),('Anna','1234'),('Anna','ABCDEF'),('Anna','１２３４５６')])
def test_registration_rejects_blank_names_and_non_six_digit_pins(owner,name,pin):
    ride=trip(owner)
    key=invitation(owner,ride)
    response=anonymous().post(f'/api/guest/{key}/register',json={'name':name,'pin':pin})
    assert response.status_code==422,response.text
    assert not db.one('SELECT id FROM passengers WHERE trip_id=?',(ride['id'],))


def test_registration_is_closed_before_start_and_after_end(owner):
    ride=trip(owner)
    key=invitation(owner,ride)
    path=f'/api/guest/{key}/register'
    guest=anonymous()
    db.execute('UPDATE trips SET starts_at=? WHERE id=?',(time.time()+600,ride['id']))
    assert guest.post(path,json={'name':'Early','pin':'012345'}).status_code==403
    db.execute('UPDATE trips SET starts_at=?,ends_at=? WHERE id=?',(time.time()-600,time.time()-1,ride['id']))
    assert guest.post(path,json={'name':'Late','pin':'012345'}).status_code==403
    assert not db.one('SELECT id FROM passengers WHERE trip_id=?',(ride['id'],))


def test_end_during_pin_hashing_does_not_create_a_guest(owner,monkeypatch):
    ride=trip(owner)
    key=invitation(owner,ride)
    original=main.pin_hash
    def finishing_hash(pin):
        db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time(),ride['id']))
        return original(pin)
    monkeypatch.setattr(main,'pin_hash',finishing_hash)
    response=anonymous().post(f'/api/guest/{key}/register',json={'name':'Late','pin':'012345'})
    assert response.status_code==403,response.text
    assert not db.one("SELECT id FROM users WHERE provider='guest'")
    assert not db.one('SELECT id FROM passengers WHERE trip_id=?',(ride['id'],))


def test_concurrent_registration_of_same_name_creates_one_identity(owner):
    ride=trip(owner)
    key=invitation(owner,ride)
    def register(pin):
        return anonymous().post(f'/api/guest/{key}/register',json={'name':'Concurrent guest','pin':pin}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(register,['012345','654321']))
    assert sorted(results)==[200,409]
    assert len(db.all_rows('SELECT id FROM passengers WHERE trip_id=?',(ride['id'],)))==1
    assert len(db.all_rows("SELECT id FROM users WHERE provider='guest'"))==1
    assert len(db.all_rows("SELECT user_id FROM members WHERE trip_id=? AND role='passenger'",(ride['id'],)))==1


def test_registration_rate_limit_keeps_existing_guest_identity(owner):
    ride=trip(owner)
    key=invitation(owner,ride)
    guest=anonymous()
    path=f'/api/guest/{key}/register'
    assert guest.post(path,json={'name':'Anna','pin':'012345'}).status_code==200
    for _ in range(19):
        assert guest.post(path,json={'name':'Anna','pin':'654321'}).status_code==409
    assert guest.post(path,json={'name':'Next','pin':'654321'}).status_code==429
    assert len(db.all_rows('SELECT id FROM passengers WHERE trip_id=?',(ride['id'],)))==1
