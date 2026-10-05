import asyncio
import base64
import json
import time
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest
from app import db, push
from app.config import settings
from app.security import cipher
from .conftest import new_driver
from .test_access import trip, passenger


def subscription(endpoint='https://fcm.googleapis.com/fcm/send/test-device'):
    public = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
    return {'endpoint':endpoint,'keys':{'p256dh':encode(public),'auth':encode(b'0123456789abcdef')}}


@pytest.fixture
def configured(owner, monkeypatch):
    monkeypatch.setattr(settings,'vapid_private_key','test-private-key')
    monkeypatch.setattr(settings,'vapid_public_key','test-public-key')
    # Exercise deliveries deterministically, without sending external notifications.
    async def no_worker():
        await asyncio.Event().wait()
    monkeypatch.setattr(push,'process_outbox',no_worker)
    return owner


@pytest.mark.parametrize('endpoint', [
    'http://fcm.googleapis.com/push', 'https://127.0.0.1/private',
    'https://evil.example/push', 'https://fcm.googleapis.com.evil.example/push',
    'https://user:pass@web.push.apple.com/push', 'https://web.push.apple.com:bad/push',
    'https://[invalid/push', 'https://web.push.apple.com:8780/push',
])
def test_push_rejects_arbitrary_endpoints(configured,endpoint):
    assert configured.post('/api/push/subscribe',json=subscription(endpoint)).status_code==422
    assert not db.all_rows('SELECT * FROM push_subscriptions')


def test_subscriptions_encrypted_scoped_and_removed_on_logout(configured):
    data=subscription()
    assert configured.post('/api/push/subscribe',json=data).status_code==200
    row=db.one('SELECT * FROM push_subscriptions')
    assert data['endpoint'] not in row['encrypted_subscription']
    assert json.loads(cipher().decrypt(row['encrypted_subscription'].encode()))==data
    stranger=new_driver('Anderer Fahrer')
    assert stranger.post('/api/push/subscribe',json=data).status_code==409
    assert stranger.post('/api/push/unsubscribe',json={'endpoint':data['endpoint']}).status_code==200
    assert db.one('SELECT * FROM push_subscriptions')
    assert configured.post('/auth/logout').status_code==200
    assert not db.one('SELECT * FROM push_subscriptions')


def test_chat_notification_is_queued_without_private_content(configured):
    created=trip(configured)
    friend=new_driver('Push-Freund')
    friend.post('/api/trips/join',json={'pin':created['pin']})
    assert friend.post('/api/push/subscribe',json=subscription()).status_code==200
    assert configured.post('/api/trips/'+created['id']+'/messages',json={'text':'Geheime private Nachricht'}).status_code==200
    job=db.one('SELECT * FROM push_outbox')
    assert job['user_id']==friend.get('/api/me').json()['id']
    assert 'Geheime' not in job['payload']
    assert json.loads(job['payload'])['url']=='/trip/'+created['id']


def test_guest_push_is_bounded_and_ended_trip_is_not_sent(configured,monkeypatch):
    created=trip(configured)
    guest,_,_=passenger(configured,created)
    result=guest.post('/api/push/subscribe',json=subscription('https://web.push.apple.com/test-device'))
    assert result.status_code==200
    assert result.json()['expires_at']<=created['ends_at']
    configured.post('/api/trips/'+created['id']+'/messages',json={'text':'Hallo'})
    db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time()-1,created['id']))
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    # Invoke the real worker function captured before the deterministic fixture patch.
    asyncio.run(real_process())
    assert sent==[]
    assert not db.one('SELECT * FROM push_outbox')


def test_outbox_delivery_calls_webpush_and_clears_job(configured,monkeypatch):
    configured.post('/api/push/subscribe',json=subscription())
    uid=configured.get('/api/me').json()['id']
    push.enqueue(uid,'Neue Einladung.')
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    asyncio.run(real_process())
    assert len(sent)==1
    assert sent[0]['timeout']==10 and sent[0]['ttl']==3600
    assert json.loads(sent[0]['data'])['body']=='Neue Einladung.'
    assert not db.one('SELECT * FROM push_outbox')


real_process=push.process_outbox


def test_push_test_targets_only_this_browser_session(configured,monkeypatch):
    data=subscription()
    other=subscription('https://web.push.apple.com/other-device')
    configured.post('/api/push/subscribe',json=data)
    configured.post('/api/push/subscribe',json=other)
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    result=configured.post('/api/push/test',json={'endpoint':data['endpoint']})
    assert result.status_code==200 and result.json()['accepted_by_provider'] is True
    assert len(sent)==1 and sent[0]['subscription_info']['endpoint']==data['endpoint']
    assert json.loads(sent[0]['data'])['tag']=='teslatalk-test'
    stranger=new_driver('Not recipient')
    assert stranger.post('/api/push/test',json={'endpoint':data['endpoint']}).status_code==404
    # Even the same account must rebind this device after a new browser login.
    assert configured.post('/api/demo/login',json={'query':'Fahrtleiter'}).status_code==200
    assert configured.post('/api/push/test',json={'endpoint':data['endpoint']}).status_code==404
    # A valid key must not substitute for the browser session.
    key=configured.post('/api/keys',json={'label':'No browser push'}).json()
    assert configured.post('/api/push/test',headers={'authorization':'Bearer '+key['token']},json={'endpoint':data['endpoint']}).status_code==403
    assert len(sent)==1


@pytest.mark.parametrize('status',[404,410,403])
def test_push_test_handles_provider_rejection_without_leaking_secrets(configured,monkeypatch,status):
    from requests import Response
    data=subscription(); configured.post('/api/push/subscribe',json=data)
    response=Response(); response.status_code=status
    def reject(**kwargs):
        raise push.WebPushException('private-provider-response',response=response)
    monkeypatch.setattr(push,'webpush',reject)
    result=configured.post('/api/push/test',json={'endpoint':data['endpoint']})
    assert result.status_code==(410 if status in (404,410) else 502)
    assert 'private-provider-response' not in result.text
    assert bool(db.one('SELECT * FROM push_subscriptions'))==(status==403)


def test_push_test_is_rate_limited_and_guest_access_ends_with_trip(configured,monkeypatch):
    data=subscription(); configured.post('/api/push/subscribe',json=data)
    monkeypatch.setattr(push,'webpush',lambda **kwargs:None)
    for _ in range(3):
        assert configured.post('/api/push/test',json={'endpoint':data['endpoint']}).status_code==200
    assert configured.post('/api/push/test',json={'endpoint':data['endpoint']}).status_code==429
    created=trip(configured); guest,_,_=passenger(configured,created)
    guest_data=subscription('https://web.push.apple.com/guest-test')
    guest.post('/api/push/subscribe',json=guest_data)
    assert guest.post('/api/push/test',json={'endpoint':guest_data['endpoint']}).status_code==200
    configured.post('/api/trips/'+created['id']+'/finish')
    assert guest.post('/api/push/test',json={'endpoint':guest_data['endpoint']}).status_code==403


def test_admin_test_broadcast_requires_admin_and_targets_all_active_devices(configured,monkeypatch):
    from .test_oidc import oidc_client
    from app.security import digest
    first=subscription(); second=subscription('https://web.push.apple.com/owner-web-app')
    configured.post('/api/push/subscribe',json=first)
    configured.post('/api/push/subscribe',json=second)
    friend=new_driver('Other push account')
    friend_data=subscription('https://web.push.apple.com/friend')
    friend.post('/api/push/subscribe',json=friend_data)
    active=trip(configured); guest,_,_=passenger(configured,active)
    guest_data=subscription('https://web.push.apple.com/active-passenger')
    guest.post('/api/push/subscribe',json=guest_data)
    ended=trip(configured); ended_guest,_,_=passenger(configured,ended)
    ended_guest.post('/api/push/subscribe',json=subscription('https://web.push.apple.com/ended-passenger'))
    configured.post('/api/trips/'+ended['id']+'/finish')
    expired=subscription('https://web.push.apple.com/expired-device')
    configured.post('/api/push/subscribe',json=expired)
    db.execute('UPDATE push_subscriptions SET expires_at=? WHERE endpoint_hash=?',(time.time()-1,digest(expired['endpoint'])))
    assert configured.post('/api/admin/push/test').status_code==401
    assert not db.all_rows('SELECT * FROM push_outbox')
    oidc_client(monkeypatch,{'sub':'operator','groups':['admin']})
    assert configured.get('/auth/admin/callback',follow_redirects=False).status_code==303
    result=configured.post('/api/admin/push/test')
    assert result.status_code==200
    assert result.json()=={'ok':True,'queued_accounts':3,'queued_devices':4}
    assert len(db.all_rows('SELECT * FROM push_outbox'))==3
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    # A passenger's trip ending after the broadcast was queued still blocks delivery.
    configured.post('/api/trips/'+active['id']+'/finish')
    asyncio.run(real_process())
    assert {call['subscription_info']['endpoint'] for call in sent}=={first['endpoint'],second['endpoint'],friend_data['endpoint']}
    assert all(json.loads(call['data'])['tag']=='teslatalk-admin-test' for call in sent)
    assert not db.all_rows('SELECT * FROM push_outbox')


def test_admin_test_skips_expired_sessions_and_is_rate_limited(configured,monkeypatch):
    from .test_oidc import oidc_client
    configured.post('/api/push/subscribe',json=subscription())
    uid=configured.get('/api/me').json()['id']
    oidc_client(monkeypatch,{'sub':'operator','groups':['admin']})
    configured.get('/auth/admin/callback',follow_redirects=False)
    db.execute("UPDATE sessions SET expires_at=? WHERE user_id=? AND kind='user'",(time.time()-1,uid))
    for _ in range(3):
        result=configured.post('/api/admin/push/test')
        assert result.status_code==200 and result.json()['queued_devices']==0
    assert configured.post('/api/admin/push/test').status_code==429
    assert not db.all_rows('SELECT * FROM push_outbox')
