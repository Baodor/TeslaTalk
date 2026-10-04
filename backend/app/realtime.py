import asyncio
import time
import httpx
import jwt
from .config import settings
from . import db
from .security import authenticate


class Hub:
    def __init__(self):
        self.rooms = {}

    def add(self, trip_id, socket, user_id):
        self.rooms.setdefault(trip_id, {})[socket] = user_id

    def remove(self, trip_id, socket):
        self.rooms.get(trip_id, {}).pop(socket, None)
        if not self.rooms.get(trip_id):
            self.rooms.pop(trip_id, None)

    def online(self):
        return {uid for sockets in self.rooms.values() for uid in sockets.values()}

    async def broadcast(self, trip_id, message):
        for socket in list(self.rooms.get(trip_id, {})):
            try:
                identity = authenticate(socket.headers, socket.cookies)
                trip = db.one('SELECT * FROM trips WHERE id=?', (trip_id,))
                end = min(trip['ends_at'], trip['finished_at'] or trip['ends_at'])
                if identity.user['provider'] == 'guest' and not trip['starts_at'] <= time.time() < end:
                    await socket.close(code=1008)
                    self.remove(trip_id, socket)
                    continue
                await asyncio.wait_for(socket.send_json(message), timeout=3)
            except Exception:
                self.remove(trip_id, socket)


hub = Hub()


def voice_token(trip_id, identity, expires_at):
    now = int(time.time())
    return jwt.encode({
        'iss':settings.livekit_key, 'sub':identity.user['id'], 'name':identity.user['display_name'],
        'nbf':now-5, 'iat':now, 'exp':min(now+120, int(expires_at)),
        'video':{'roomJoin':True, 'room':'trip-'+trip_id, 'canPublish':True, 'canSubscribe':True,
                 'canPublishSources':['microphone'], 'canPublishData':False},
    }, settings.livekit_secret, algorithm='HS256')


async def room_control(method, trip_id):
    now = int(time.time())
    token = jwt.encode({'iss':settings.livekit_key, 'sub':'teslatalk-server', 'nbf':now-5, 'exp':now+60,
                        'video':{'roomCreate':True}}, settings.livekit_secret, algorithm='HS256')
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            payload = {'room':'trip-'+trip_id} if method == 'DeleteRoom' else {'name':'trip-'+trip_id, 'empty_timeout':300}
            response = await client.post(settings.livekit_internal_url+'/twirp/livekit.RoomService/'+method,
                                         headers={'Authorization':'Bearer '+token}, json=payload)
        return response.status_code == 200 or method == 'DeleteRoom' and response.status_code == 404
    except httpx.HTTPError:
        return False


async def ensure_voice_room(trip_id):
    return await room_control('CreateRoom', trip_id)


async def delete_voice_room(trip_id):
    if not settings.voice_ready:
        return True
    return await room_control('DeleteRoom', trip_id)
