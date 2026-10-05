import asyncio
import time
from app import db,accounts
from app.main import clean_deleted_voice
from app.security import digest
from .conftest import new_driver
from .test_passenger_tesla import guest_trip


def admin(client,subject='independent-admin'):
    cookie='delete-admin-cookie'
    db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(digest(cookie),subject,'admin',time.time()+60))
    client.cookies.set('tt_admin',cookie)


def test_delete_requires_admin_and_exact_username_then_revokes_session_and_bearer(owner):
    user=owner.get('/api/me').json()
    token=owner.post('/api/keys',json={'label':'Deletion test','days':None}).json()['token']
    path='/api/admin/users/'+user['id']
    assert owner.request('DELETE',path,json={'username':user['username']}).status_code==401
    admin(owner,user['id'])
    assert owner.request('DELETE',path,headers={'authorization':'Bearer '+token},json={'username':user['username']}).status_code==401
    assert owner.request('DELETE',path,json={'username':'wrong'}).status_code==409
    assert owner.get('/api/me').status_code==200
    response=owner.request('DELETE',path,json={'username':user['username']})
    assert response.status_code==200,response.text
    assert not db.one('SELECT id FROM users WHERE id=?',(user['id'],))
    assert owner.get('/api/me').status_code==401
    assert owner.get('/api/me',headers={'authorization':'Bearer '+token}).status_code==401
    assert owner.get('/api/admin').status_code==200  # Admin namespace remains independent.
    assert owner.request('DELETE',path,json={'username':user['username']}).status_code==404


def test_deletion_removes_owned_trips_qr_data_and_planner_but_keeps_foreign_group(owner):
    guest,owned,_=guest_trip(owner)
    uid=owner.get('/api/me').json()['id']
    guest_id=guest.get('/api/me').json()['id']
    other=new_driver('Other deletion driver')
    _,foreign,_=guest_trip(other)
    other_id=other.get('/api/me').json()['id']
    assert owner.post('/api/trips/join',json={'pin':foreign['pin']}).status_code==200
    vehicle=owner.get('/api/me').json()['favorite_vehicle']
    db.execute('INSERT INTO trip_planners VALUES (?,?,?)',(foreign['id'],uid,vehicle))
    db.execute('INSERT INTO trip_navigation VALUES (?,?,?)',(foreign['id'],vehicle,'{}'))
    db.execute('INSERT INTO route_followers(trip_id,user_id,vehicle_id,accepted_at) VALUES (?,?,?,?)',(foreign['id'],uid,vehicle,time.time()))
    db.execute('INSERT INTO credentials VALUES (?,?)',(uid,'encrypted-test-token'))
    db.execute('INSERT INTO tesla_profile_links VALUES (?,?,?)',(guest_id,'linked-tesla-id',time.time()))
    low,high=sorted([uid,other_id])
    db.execute('INSERT INTO friendships VALUES (?,?,?,?,?)',(low,high,uid,'accepted',time.time()))
    for trip in (owned,foreign):
        db.execute('INSERT INTO control_grants VALUES (?,?,?,?)',(trip['id'],uid,vehicle,time.time()))
        db.execute('INSERT INTO control_batches VALUES (?,?,?,?,?,?,?)',(trip['id'],'old-comfort-request',uid if trip==owned else other_id,'{}','{}','completed',time.time()))
        assert owner.post('/api/trips/'+trip['id']+'/messages',json={'text':'Delete my message'}).status_code==200
        assert owner.post('/api/trips/'+trip['id']+'/samples',json={'source':'browser','latitude':50,'longitude':8}).status_code==200
    admin(other)
    response=other.request('DELETE','/api/admin/users/'+uid,json={'username':owner.get('/api/me').json()['username']})
    assert response.status_code==200,response.text
    assert response.json()['deleted_trips']==1 and response.json()['deleted_qr_accounts']==1
    assert not db.one('SELECT id FROM trips WHERE id=?',(owned['id'],))
    assert not db.one('SELECT id FROM users WHERE id=?',(guest_id,))
    assert other.get('/api/trips/'+foreign['id']).status_code==200
    assert owner.get('/api/me').status_code==401 and guest.get('/api/me').status_code==401
    assert not db.one('SELECT * FROM trip_planners WHERE trip_id=?',(foreign['id'],))
    assert not db.one('SELECT * FROM trip_navigation WHERE trip_id=?',(foreign['id'],))
    assert not db.one('SELECT * FROM messages WHERE user_id=?',(uid,))
    assert not db.one('SELECT * FROM samples WHERE user_id=?',(uid,))
    assert not db.one('SELECT * FROM control_grants WHERE user_id=?',(uid,))
    assert not db.one('SELECT * FROM control_batches')
    assert not db.one('SELECT * FROM friendships WHERE low_id=? OR high_id=?',(uid,uid))
    assert db.one('SELECT * FROM voice_removals WHERE trip_id=? AND user_id=?',(foreign['id'],uid))
    assert db.one('SELECT * FROM voice_room_deletions WHERE trip_id=?',(owned['id'],))
    with db.connect() as connection:assert not connection.execute('PRAGMA foreign_key_check').fetchall()


def test_failed_dependency_deletion_rolls_back_everything(owner):
    _,trip,_=guest_trip(owner)
    user=owner.get('/api/me').json()
    token=owner.post('/api/keys',json={'label':'Rollback','days':None}).json()['token']
    with db.connect() as connection:
        connection.execute('CREATE TABLE future_dependency(user_id TEXT REFERENCES users(id))')
        connection.execute('INSERT INTO future_dependency VALUES (?)',(user['id'],))
    admin(owner)
    response=owner.request('DELETE','/api/admin/users/'+user['id'],json={'username':user['username']})
    assert response.status_code==409
    assert owner.get('/api/me',headers={'authorization':'Bearer '+token}).status_code==200
    assert owner.get('/api/trips/'+trip['id']).status_code==200
    assert db.one('SELECT id FROM users WHERE id=?',(user['id'],))


def test_voice_cleanup_retries_through_old_token_deadline_and_service_failure(client,monkeypatch):
    deadline=time.time()-1
    db.execute('INSERT INTO voice_removals VALUES (?,?,?)',('old-trip','old-user',deadline))
    db.execute('INSERT INTO voice_room_deletions VALUES (?,?)',('owned-trip',time.time()+125))
    calls=[]
    async def failed(trip,user):calls.append((trip,user));return False
    async def deleted(trip):calls.append((trip,None));return True
    monkeypatch.setattr('app.main.remove_voice_participant',failed)
    monkeypatch.setattr('app.main.delete_voice_room',deleted)
    asyncio.run(clean_deleted_voice())
    assert db.one('SELECT * FROM voice_removals') and db.one('SELECT * FROM voice_room_deletions')
    async def success(trip,user):return True
    monkeypatch.setattr('app.main.remove_voice_participant',success)
    asyncio.run(clean_deleted_voice())
    assert not db.one('SELECT * FROM voice_removals')
    db.execute('UPDATE voice_room_deletions SET expires_at=?',(time.time()-1,))
    asyncio.run(clean_deleted_voice())
    assert not db.one('SELECT * FROM voice_room_deletions')
