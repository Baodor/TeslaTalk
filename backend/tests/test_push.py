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
