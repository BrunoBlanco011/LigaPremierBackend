import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import get_settings
from app.core.middleware import client_ip
from app.core.realtime import RealtimeHub

router = APIRouter()


def _origin_allowed(websocket: WebSocket) -> bool:
    # CORS no aplica a WebSockets: el navegador siempre manda Origin y aqui se valida a mano.
    # Clientes que no son navegador no mandan Origin y se aceptan (el canal solo anuncia cambios).
    origin = websocket.headers.get("origin")
    allowed = get_settings().cors_origins
    return origin is None or not allowed or "*" in allowed or origin in allowed


@router.websocket("/ws")
async def realtime_updates(websocket: WebSocket) -> None:
    """Canal publico de cambios. Mensajes del servidor: `hello`, `change` y `pong` (si el cliente manda "ping")."""
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    hub: RealtimeHub = websocket.app.state.realtime
    subscriber = hub.subscribe(client_ip(websocket.scope, get_settings().trust_proxy_headers))
    if subscriber is None:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    async def forward_events() -> None:
        while (event := await subscriber.queue.get()) is not None:
            await websocket.send_json(event)
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)

    async def read_client() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text") == "ping":
                subscriber.queue.put_nowait({"type": "pong"})

    try:
        await websocket.accept()
        await websocket.send_json({"type": "hello"})
        tasks = [asyncio.create_task(forward_events()), asyncio.create_task(read_client())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, asyncio.QueueFull):
        pass  # el cliente se fue a medio envio
    finally:
        hub.unsubscribe(subscriber)
