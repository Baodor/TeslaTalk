import time
from app import db
from app.security import digest
from .conftest import new_driver


def test_admin_list_contains_requested_fields_and_requires_admin_session(owner):
    me=owner.get('/api/me').json()
    db.execute("UPDATE users SET provider='tesla',email=?,avatar_url=?,plate=? WHERE id=?",('tesla@example.test','https://images.example.test/profile.png','HHTT123',me['id']))
    assert owner.get('/api/admin/users').status_code==401
    token=owner.post('/api/keys',json={'label':'User cannot administer','days':1}).json()['token']
    assert owner.get('/api/admin/users',headers={'authorization':'Bearer '+token}).status_code==401
    before=time.time()
    friend=new_driver('Another user')
    friend_id=friend.get('/api/me').json()['id']
    db.execute('UPDATE users SET last_login_at=NULL WHERE id=?',(me['id'],))
    admin_cookie='isolated-admin-user-list'
    db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(digest(admin_cookie),'test-admin','admin',time.time()+60))
    owner.cookies.set('tt_admin',admin_cookie)
    response=owner.get('/api/admin/users')
    assert response.status_code==200,response.text
    accounts=response.json()
    assert {account['id'] for account in accounts}=={me['id'],friend_id}
    account=next(account for account in accounts if account['id']==me['id'])
    assert set(account)=={'id','provider','display_name','username','email','plate','avatar_url','created_at','last_login_at'}
    assert account['email']=='tesla@example.test' and account['plate']=='HHTT123'
    assert account['avatar_url']=='https://images.example.test/profile.png'
    assert account['last_login_at'] is None
    assert before<=next(account for account in accounts if account['id']==friend_id)['last_login_at']<=time.time()
    assert token not in response.text and 'encrypted_token' not in response.text and 'pin_hash' not in response.text


def test_last_login_changes_only_on_sign_in_not_profile_reads(owner):
    me=owner.get('/api/me').json()
    first=db.one('SELECT last_login_at FROM users WHERE id=?',(me['id'],))['last_login_at']
    assert first is not None
    owner.get('/api/me')
    owner.get('/api/trips')
    assert db.one('SELECT last_login_at FROM users WHERE id=?',(me['id'],))['last_login_at']==first
    db.execute('UPDATE users SET last_login_at=? WHERE id=?',(first-60,me['id']))
    assert owner.post('/api/demo/login',json={'query':'Fahrtleiter'}).status_code==200
    assert db.one('SELECT last_login_at FROM users WHERE id=?',(me['id'],))['last_login_at']>=first
