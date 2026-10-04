import os
os.environ.setdefault('APP_SECRET', 'test-secret-not-for-production-'+'a'*40)
os.environ.setdefault('DEMO_MODE', 'true')

import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
from app.security import limiter
from app.realtime import hub


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings,'db_path',str(tmp_path/'test.sqlite'))
    monkeypatch.setattr(settings,'app_url','http://testserver')
    monkeypatch.setattr(settings,'demo',True)
    monkeypatch.setattr(settings,'livekit_key','')
    monkeypatch.setattr(settings,'livekit_secret','')
    limiter.windows.clear()
    hub.rooms.clear()
    with TestClient(app,headers={'origin':'http://testserver'}) as client:
        yield client


def new_driver(name):
    client=TestClient(app,headers={'origin':'http://testserver'})
    assert client.post('/api/demo/login',json={'query':name}).status_code==200
    return client


@pytest.fixture
def owner(client):
    assert client.post('/api/demo/login',json={'query':'Fahrtleiter'}).status_code==200
    return client
