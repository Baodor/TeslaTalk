import asyncio
import time
import pytest
from app import main
from app.navigation import empty_navigation
from app.realtime import hub
from .conftest import new_driver
from .test_passenger_tesla import guest_trip


@pytest.mark.parametrize('viewer',['driver','passenger'])
def test_group_viewer_receives_all_driver_cars_when_their_browsers_are_closed(owner,monkeypatch,viewer):
    guest,ride,_=guest_trip(owner)
    friend=new_driver('Offline map driver')
    assert friend.post('/api/trips/join',json={'pin':ride['pin']}).status_code==200
    users=[owner.get('/api/me').json(),friend.get('/api/me').json()]
    observer=owner if viewer=='driver' else guest
    uid=observer.get('/api/me').json()['id']
    fetched=[]
    async def fetch(user_id,vehicle):
        fetched.append(user_id)
        return {'latitude':49+len(fetched),'longitude':8.65,'battery_pct':60,'source':'fleet','updated_at':time.time()}
    async def navigation(*args):return empty_navigation()
    async def broadcast(*args):pass
    monkeypatch.setattr(main.fleet,'fetch_vehicle',fetch)
    monkeypatch.setattr(main.fleet,'fetch_navigation',navigation)
    monkeypatch.setattr(hub,'broadcast',broadcast)
    monkeypatch.setattr(hub,'rooms',{})
    asyncio.run(main.background_cycle(0))
    assert fetched==[]  # No open group: no new paid vehicle polling.
    hub.rooms[ride['id']]={object():uid}
    asyncio.run(main.background_cycle(0))
    assert set(fetched)=={user['id'] for user in users} and len(fetched)==2
    for client in (owner,friend,guest):
        rows=client.get('/api/trips/'+ride['id']).json()['participants_detail']
        cars=[row for row in rows if row['role']=='driver']
        assert {car['id'] for car in cars}=={user['id'] for user in users}
        assert all(car['data']['latitude'] is not None and car['data']['longitude']==8.65 for car in cars)
        assert all(row['vehicle_id'] is None and row['data']=={} for row in rows if row['role']=='passenger')
    fetched.clear()
    hub.rooms.clear()
    asyncio.run(main.background_cycle(0))
    assert fetched==[]
