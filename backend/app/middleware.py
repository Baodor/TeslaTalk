from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_REQUEST_BYTES = 1_048_576


class BodyLimitMiddleware:
    """Bound bytes actually read, including requests without Content-Length."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > MAX_REQUEST_BYTES:
                    raise HTTPException(413, 'Anfrage zu groß.')
            return message

        await self.app(scope, limited_receive, send)
