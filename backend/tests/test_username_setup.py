import sqlite3
from app import db
from app.config import settings
from .conftest import new_driver


def test_existing_volume_marks_only_generated_tesla_names_and_migration_is_idempotent(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'db_path',str(tmp_path/'old.sqlite'))
    old_schema=db.SCHEMA.replace(', username_chosen INTEGER NOT NULL DEFAULT 1','').replace(', last_login_at REAL','')
    with sqlite3.connect(settings.db_path) as connection:
        connection.executescript(old_schema)
        for uid,provider,username in [('12345678-old','tesla','fahrer-12345678'),('chosen','tesla','ChosenName'),('demo','demo','demo-name')]:
            connection.execute('INSERT INTO users(id,provider,subject,username,display_name,created_at) VALUES (?,?,?,?,?,?)',(uid,provider,uid,username,username,123))
    db.initialize()
    assert db.one('SELECT * FROM users WHERE id=?',('12345678-old',))['username_chosen']==0
    assert db.one('SELECT * FROM users WHERE id=?',('chosen',))['username_chosen']==1
    assert db.one('SELECT * FROM users WHERE id=?',('demo',))['username_chosen']==1
    assert db.one('SELECT * FROM users WHERE id=?',('chosen',))['last_login_at'] is None
    db.execute('UPDATE users SET username_chosen=1 WHERE id=?',('12345678-old',))
    db.initialize()
    assert db.one('SELECT * FROM users WHERE id=?',('12345678-old',))['username_chosen']==1


def test_tesla_username_is_required_and_collision_does_not_complete_setup(owner):
    me=owner.get('/api/me').json()
    other=new_driver('Existing username owner')
    assert other.patch('/api/me',json={'username':'TakenName','display_name':'Other'}).status_code==200
    db.execute("UPDATE users SET provider='tesla',username_chosen=0 WHERE id=?",(me['id'],))
    assert owner.get('/api/me').json()['needs_username'] is True
    assert owner.get('/api/vehicles').status_code==409
    conflict=owner.patch('/api/me',json={'username':'takenNAME','display_name':'Tesla driver'})
    assert conflict.status_code==409 and 'Benutzername' in conflict.json()['detail']
    assert owner.get('/api/me').json()['needs_username'] is True
    response=owner.patch('/api/me',json={'username':'MyUniqueName','display_name':'Tesla driver','plate':'HH TT 123'})
    assert response.status_code==200,response.text
    assert response.json()['needs_username'] is False
    assert response.json()['username']=='MyUniqueName'
    assert response.json()['plate']=='HHTT123'
    assert owner.get('/api/vehicles').status_code==200
    assert owner.get('/api/me').json()['needs_username'] is False
