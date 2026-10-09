"""Notificaciones en tiempo real por WebSocket.

Cada peticion que modifica datos (POST/PUT/PATCH/DELETE con respuesta 2xx) se anuncia a
todos los clientes conectados a `/api/v1/ws` como un evento ligero:

    {"type": "change", "resource": "matches", "action": "updated",
     "id": "<uuid>", "tournament_id": null, "path": "/api/v1/matches/<uuid>/result"}

El evento no lleva los datos: el frontend vuelve a pedir por HTTP lo que tenga en pantalla.
Asi el WebSocket no puede filtrar informacion que el usuario no podria leer por la API.

El hub vive en memoria: con varios workers de uvicorn cada uno tiene sus propios clientes.
"""

import asyncio
import logging
import threading
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.realtime")

_ACTIONS = {"POST": "created", "PUT": "updated", "PATCH": "updated", "DELETE": "deleted"}
# Datos privados (solo admin o del propio usuario) y rutas con el token secreto de una
# invitacion: no se anuncian en el canal publico
_PRIVATE_RESOURCES = {"auth", "users", "me", "finance", "invites"}

Event = dict[str, Any]


def build_change_event(method: str, path: str, prefix: str) -> Event | None:
    action = _ACTIONS.get(method)
    if action is None or not path.startswith(prefix + "/"):
        return None
    segments = [s for s in path[len(prefix):].split("/") if s]
    if not segments or _PRIVATE_RESOURCES.intersection(segments):
        return None

    resource = segments[0]
    tournament_id = segments[1] if resource == "tournaments" and len(segments) > 1 else None
    # /tournaments/{id}/matches -> el recurso afectado es "matches" (y se indica el torneo)
    if tournament_id and len(segments) > 2:
        resource = segments[2]
    return {
        "type": "change",
        "resource": resource,
        "action": action,
        "id": segments[1] if len(segments) > 1 and resource == segments[0] else None,
        "tournament_id": tournament_id,
        "path": path,
    }


class _Subscriber:
    __slots__ = ("queue", "loop", "ip")

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, ip: str) -> None:
        self.queue = queue
        self.loop = loop
        self.ip = ip


class RealtimeHub:
    """Lista de clientes conectados. `publish` se puede llamar desde cualquier hilo."""

    def __init__(self, max_connections: int, max_per_ip: int, queue_size: int = 100) -> None:
        self.max_connections = max_connections
        self.max_per_ip = max_per_ip
        self.queue_size = queue_size
        self._subscribers: set[_Subscriber] = set()
        self._lock = threading.Lock()

    @property
    def connections(self) -> int:
        return len(self._subscribers)

    def subscribe(self, ip: str) -> _Subscriber | None:
        """Registra un cliente; None si se alcanzo el limite total o por IP."""
        with self._lock:
            if len(self._subscribers) >= self.max_connections:
                return None
            if sum(1 for s in self._subscribers if s.ip == ip) >= self.max_per_ip:
                return None
            subscriber = _Subscriber(asyncio.Queue(self.queue_size), asyncio.get_running_loop(), ip)
            self._subscribers.add(subscriber)
            return subscriber

    def unsubscribe(self, subscriber: _Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, event: Event) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(self._deliver, subscriber, event)
            except RuntimeError:  # su event loop ya se cerro
                self.unsubscribe(subscriber)

    def _deliver(self, subscriber: _Subscriber, event: Event) -> None:
        try:
            subscriber.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Cliente que no lee: se le desconecta en lugar de acumular memoria
            logger.warning("Cliente WebSocket lento desconectado ip=%s", subscriber.ip)
            self.unsubscribe(subscriber)
            while not subscriber.queue.empty():
                subscriber.queue.get_nowait()
            subscriber.queue.put_nowait(None)


class RealtimeEventsMiddleware:
    """Publica un evento por cada peticion de escritura que termino con exito."""

    def __init__(self, app: ASGIApp, hub: RealtimeHub, prefix: str) -> None:
        self.app = app
        self.hub = hub
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _ACTIONS:
            await self.app(scope, receive, send)
            return

        status = 0

        async def tracking_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        await self.app(scope, receive, tracking_send)
        if 200 <= status < 300:
            event = build_change_event(scope["method"], scope.get("path", ""), self.prefix)
            if event is not None:
                self.hub.publish(event)
