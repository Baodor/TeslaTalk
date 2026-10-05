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
    assert sent[0]['headers']=={'Urgency':'high'}
    assert json.loads(sent[0]['data'])['body']=='Neue Einladung.'
    assert not db.one('SELECT * FROM push_outbox')


real_process=push.process_outbox


def test_slow_device_does_not_delay_other_devices(configured,monkeypatch):
    from threading import Event
    slow=subscription('https://fcm.googleapis.com/fcm/send/slow-device')
    fast=subscription('https://web.push.apple.com/fast-device')
    configured.post('/api/push/subscribe',json=slow)
    configured.post('/api/push/subscribe',json=fast)
    push.enqueue(configured.get('/api/me').json()['id'],'Neue Einladung.')
    fast_started=Event()
    slow_observed_fast=[]
    def deliver(data,payload):
        if data['endpoint']==slow['endpoint']:
            slow_observed_fast.append(fast_started.wait(1))
        else:
            fast_started.set()
    monkeypatch.setattr(push,'deliver',deliver)
    asyncio.run(real_process())
    assert slow_observed_fast==[True]
    assert not db.all_rows('SELECT * FROM push_outbox')


def test_push_batch_limits_concurrent_deliveries(configured,monkeypatch):
    for number in range(6):
        configured.post('/api/push/subscribe',json=subscription(f'https://web.push.apple.com/device-{number}'))
    push.enqueue(configured.get('/api/me').json()['id'],'Neue Einladung.')
    async def scenario():
        full,release=asyncio.Event(),asyncio.Event()
        active=peak=sent=0
        async def send(function,*args):
            nonlocal active,peak,sent
            active+=1
            peak=max(peak,active)
            if active==4:
                full.set()
            await release.wait()
            active-=1
            sent+=1
        monkeypatch.setattr(push.asyncio,'to_thread',send)
        task=asyncio.create_task(real_process())
        try:
            await asyncio.wait_for(full.wait(),1)
            await asyncio.sleep(0)
            assert active==peak==4
        finally:
            release.set()
            await task
        assert sent==6 and peak==4
    asyncio.run(scenario())
    assert not db.all_rows('SELECT * FROM push_outbox')


def test_parallel_jobs_keep_messages_ordered_on_each_device(configured,monkeypatch):
    configured.post('/api/push/subscribe',json=subscription())
    uid=configured.get('/api/me').json()['id']
    push.enqueue(uid,'Erste Nachricht.')
    push.enqueue(uid,'Zweite Nachricht.')
    async def scenario():
        first,second,release=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def send(function,data,payload):
            if json.loads(payload)['body']=='Erste Nachricht.':
                first.set()
                await release.wait()
            else:
                second.set()
        monkeypatch.setattr(push.asyncio,'to_thread',send)
        task=asyncio.create_task(real_process())
        try:
            await asyncio.wait_for(first.wait(),1)
            await asyncio.sleep(0)
            assert not second.is_set()
        finally:
            release.set()
            await task
        assert second.is_set()
    asyncio.run(scenario())


def test_retry_skips_devices_already_accepted_by_provider(configured,monkeypatch):
    from collections import Counter
    from requests import Response
    slow=subscription('https://fcm.googleapis.com/fcm/send/retry-device')
    fast=subscription('https://web.push.apple.com/accepted-device')
    configured.post('/api/push/subscribe',json=slow)
    configured.post('/api/push/subscribe',json=fast)
    push.enqueue(configured.get('/api/me').json()['id'],'Neue Einladung.')
    calls=Counter()
    def deliver(data,payload):
        calls[data['endpoint']]+=1
        if data['endpoint']==slow['endpoint'] and calls[data['endpoint']]==1:
            response=Response(); response.status_code=503
            raise push.WebPushException('private-provider-error',response=response)
    monkeypatch.setattr(push,'deliver',deliver)
    asyncio.run(real_process())
    assert db.one('SELECT * FROM push_outbox')['attempts']==1
    assert len(db.all_rows('SELECT * FROM push_deliveries'))==1
    db.execute('UPDATE push_outbox SET next_at=?',(time.time()-1,))
    asyncio.run(real_process())
    assert calls[slow['endpoint']]==2 and calls[fast['endpoint']]==1
    assert not db.all_rows('SELECT * FROM push_outbox')
    assert not db.all_rows('SELECT * FROM push_deliveries')


def test_passenger_delivery_rechecks_trip_after_waiting_for_slot(configured,monkeypatch):
    created=trip(configured); guest,_,_=passenger(configured,created)
    uid=guest.get('/api/me').json()['id']
    assert guest.post('/api/push/subscribe',json=subscription('https://web.push.apple.com/waiting-passenger')).status_code==200
    push.enqueue(uid,'Neue Nachricht.',trip_id=created['id'])
    job=db.one('SELECT * FROM push_outbox')
    endpoint=db.one('SELECT endpoint_hash FROM push_subscriptions WHERE user_id=?',(uid,))['endpoint_hash']
    sent=[]
    monkeypatch.setattr(push,'deliver',lambda *args:sent.append(args))
    async def scenario():
        slots=asyncio.Semaphore(0)
        task=asyncio.create_task(push.send_job_device(job,endpoint,slots))
        await asyncio.sleep(0)
        db.execute('UPDATE trips SET finished_at=? WHERE id=?',(time.time()-1,created['id']))
        slots.release()
        assert await task is False
    asyncio.run(scenario())
    assert sent==[]


def test_push_receipts_upgrade_preserves_existing_queued_jobs(configured):
    configured.post('/api/push/subscribe',json=subscription())
    uid=configured.get('/api/me').json()['id']
    push.enqueue(uid,'Bereits eingeplante Nachricht.')
    before=db.one('SELECT * FROM push_outbox')
    db.execute('DROP TABLE push_deliveries')
    db.initialize()
    db.initialize()
    assert db.one('SELECT * FROM push_outbox')==before
    assert configured.get('/api/me').json()['id']==uid
    assert db.all_rows('SELECT * FROM push_deliveries')==[]


def test_push_test_targets_only_this_browser_session(configured,monkeypatch):
    data=subscription()
    other=subscription('https://web.push.apple.com/other-device')
    configured.post('/api/push/subscribe',json=data)
    configured.post('/api/push/subscribe',json=other)
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    result=configured.post('/api/push/test',json={'endpoint':data['endpoint']})
    assert result.status_code==200 and result.json()['accepted_by_provider'] is True
    assert result.json()['provider_elapsed_ms']>=0
    assert abs(result.json()['provider_accepted_at']-time.time())<2
    assert len(sent)==1 and sent[0]['subscription_info']['endpoint']==data['endpoint']
    assert json.loads(sent[0]['data'])['tag'].startswith('teslatalk-test-')
    stranger=new_driver('Not recipient')
    assert stranger.post('/api/push/test',json={'endpoint':data['endpoint']}).status_code==404
    # Even the same account must rebind this device after a new browser login.
    assert configured.post('/api/demo/login',json={'query':'Fahrtleiter'}).status_code==200
    assert configured.post('/api/push/test',json={'endpoint':data['endpoint']}).status_code==404
    # A valid key must not substitute for the browser session.
    key=configured.post('/api/keys',json={'label':'No browser push'}).json()
    assert configured.post('/api/push/test',headers={'authorization':'Bearer '+key['token']},json={'endpoint':data['endpoint']}).status_code==403
    assert len(sent)==1


def test_personal_test_rebinds_and_sends_with_one_request(configured,monkeypatch):
    from app.security import digest
    data=subscription('https://web.push.apple.com/personal-one-request')
    assert configured.post('/api/push/subscribe',json=data).status_code==200
    assert configured.post('/api/demo/login',json={'query':'Fahrtleiter'}).status_code==200
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    # A renewed browser session should not need a preliminary request. On iOS,
    # the page can be suspended between that request and the actual push test.
    for _ in range(2):
        response=configured.post('/api/push/test',json=data)
        assert response.status_code==200,response.text
        assert response.json()['accepted_by_provider'] is True
    assert len(sent)==2
    assert all(call['subscription_info']==data for call in sent)
    tags=[json.loads(call['data'])['tag'] for call in sent]
    assert all(tag.startswith('teslatalk-test-') for tag in tags)
    assert len(set(tags))==2
    row=db.one('SELECT * FROM push_subscriptions WHERE endpoint_hash=?',(digest(data['endpoint']),))
    assert row['session_hash']==digest(configured.cookies.get('tt_session'))


def test_atomic_personal_test_preserves_endpoint_ownership_and_validation(configured,monkeypatch):
    data=subscription('https://web.push.apple.com/owned-personal-test')
    assert configured.post('/api/push/subscribe',json=data).status_code==200
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    stranger=new_driver('Not this device owner')
    assert stranger.post('/api/push/test',json=data).status_code==409
    assert configured.post('/api/push/test',json=subscription('https://127.0.0.1/private')).status_code==422
    assert sent==[]
    assert db.one('SELECT user_id FROM push_subscriptions')['user_id']==configured.get('/api/me').json()['id']


def test_push_worker_survives_a_temporary_database_failure(configured,monkeypatch,caplog):
    import sqlite3
    calls=[]
    async def process():
        calls.append(True)
        if len(calls)==1:
            raise sqlite3.OperationalError('private database details')
    async def tick(seconds):
        if len(calls)>=2:
            raise asyncio.CancelledError
    monkeypatch.setattr(push,'process_outbox',process)
    monkeypatch.setattr(push.asyncio,'sleep',tick)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(push.worker())
    assert len(calls)==2
    assert 'OperationalError' in caplog.text
    assert 'private database details' not in caplog.text


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
    assert all(json.loads(call['data'])['tag'].startswith('teslatalk-admin-test-') for call in sent)
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
