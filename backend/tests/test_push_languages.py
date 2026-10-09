import asyncio
import json
import pytest
from app import db, push
from app.security import cipher
from .test_push import configured, subscription, real_process


@pytest.mark.parametrize('language,title,body', [
    ('de','TeslaTalk · Testnachricht','Deine Benachrichtigungen erreichen dieses Gerät.'),
    ('en','TeslaTalk · Test notification','Your notifications reach this device.'),
    ('nl','TeslaTalk · Testmelding','Je meldingen bereiken dit apparaat.'),
    ('de-AT','TeslaTalk · Servas, des is a Test','Deine Benachrichtigungen kumman auf dem Gerät an.'),
])
def test_personal_test_uses_device_language(configured,monkeypatch,language,title,body):
    data=subscription() | {'language':language}
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    assert configured.post('/api/push/test',json=data).status_code==200
    assert json.loads(sent[0]['data'])['title']==title
    assert json.loads(sent[0]['data'])['body']==body
    assert sent[0]['subscription_info']=={'endpoint':data['endpoint'],'keys':data['keys']}
    stored=json.loads(cipher().decrypt(db.one('SELECT * FROM push_subscriptions')['encrypted_subscription'].encode()))
    assert stored['language']==language


def test_one_account_receives_broadcast_in_each_devices_language(configured,monkeypatch):
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    for language in ('de','en','nl','de-AT'):
        data=subscription('https://web.push.apple.com/device-'+language) | {'language':language}
        assert configured.post('/api/push/subscribe',json=data).status_code==200
    assert push.test_all_devices()['queued_devices']==4
    asyncio.run(real_process())
    bodies={item['subscription_info']['endpoint'].split('/device-',1)[-1]:json.loads(item['data'])['body'] for item in sent}
    assert bodies=={'de':'Deine TeslaTalk-Administration testet die Benachrichtigungen.','en':'Your TeslaTalk administrator is testing notifications.','nl':'Je TeslaTalk-beheerder test de meldingen.','de-AT':'Dei TeslaTalk-Verwaltung probiert de Benachrichtigungen aus.'}
    assert not db.one('SELECT * FROM push_outbox')


@pytest.mark.parametrize('language,title',[('nl','TeslaTalk · Testmelding'),('de-AT','TeslaTalk · Servas, des is a Test')])
def test_language_can_change_and_older_client_does_not_reset_it(configured,monkeypatch,language,title):
    data=subscription()
    assert configured.post('/api/push/subscribe',json=data | {'language':'en'}).status_code==200
    assert configured.post('/api/push/subscribe',json=data | {'language':language}).status_code==200
    assert configured.post('/api/push/subscribe',json=data).status_code==200
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    assert configured.post('/api/push/test',json={'endpoint':data['endpoint']}).status_code==200
    assert json.loads(sent[0]['data'])['title']==title
    assert len(db.all_rows('SELECT * FROM push_subscriptions'))==1


@pytest.mark.parametrize('language',['fr','nl-BE','auto',''])
def test_push_language_must_be_supported(configured,language):
    assert configured.post('/api/push/subscribe',json=subscription() | {'language':language}).status_code==422
    assert not db.one('SELECT * FROM push_subscriptions')


@pytest.mark.parametrize('language,template',[('nl','{name}: nieuw bericht in ‘{title}’.'),('de-AT','{name}: neue Nachricht in „{title}“.')])
def test_notification_templates_preserve_user_text_and_private_chat_stays_out(configured,monkeypatch,language,template):
    data=subscription() | {'language':language}
    configured.post('/api/push/subscribe',json=data)
    name='Karte';title='Route: neue Nachricht in „Wald“'
    uid=configured.get('/api/me').json()['id']
    push.enqueue(uid,name+': neue Nachricht in „'+title+'“.',message_key='chat',parameters={'name':name,'title':title})
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    asyncio.run(real_process())
    result=json.loads(sent[0]['data'])
    assert result['body']==template.format(name=name,title=title)
    assert set(result)=={'title','body','url','tag'}


@pytest.mark.parametrize('body,expected',[
    ('Karte möchte sich mit dir verbinden.','Karte mag si mit dir verbinden.'),
    ('Du bist zur Fahrt „Verlauf {0}“ eingeladen.','Du bist zur Fahrt „Verlauf {0}“ eingladn.'),
    ('Karte: neue Nachricht in „Verlauf {0}“.','Karte: neue Nachricht in „Verlauf {0}“.'),
    ('Eine übernommene Fahrzeugroute weicht ab oder kann nicht gefahren werden. Bitte Routenübersicht prüfen.','A übernommene Autoroute weicht ab oder geht si ned aus. Schau bitte de Routenübersicht an.'),
])
def test_austrian_satire_supports_queued_legacy_messages_without_rewriting_names(body,expected):
    payload=json.dumps({'title':'TeslaTalk','body':body,'url':'/','tag':'teslatalk'})
    result=json.loads(push.localize_payload(payload,'de-AT'))
    assert result=={'title':'TeslaTalk','body':expected,'url':'/','tag':'teslatalk'}


def test_legacy_subscription_defaults_to_german(configured,monkeypatch):
    data=subscription()
    configured.post('/api/push/subscribe',json=data)
    sent=[]
    monkeypatch.setattr(push,'webpush',lambda **kwargs:sent.append(kwargs))
    configured.post('/api/push/test',json={'endpoint':data['endpoint']})
    assert json.loads(sent[0]['data'])['title']=='TeslaTalk · Testnachricht'
