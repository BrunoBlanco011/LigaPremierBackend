"""Middlewares de seguridad (ASGI puro, sin dependencias extra).

- SecurityHeadersMiddleware: cabeceras recomendadas por OWASP para APIs.
- BodySizeLimitMiddleware: rechaza cuerpos demasiado grandes (413).
- RateLimitMiddleware: limite global de peticiones por IP (429).
"""

import json
import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.rate_limit import SlidingWindowLimiter

logger = logging.getLogger("app.security")

# Swagger/ReDoc cargan scripts y estilos del CDN: ahi no se aplica la CSP estricta
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def client_ip(scope: Scope, trust_proxy_headers: bool) -> str:
    """IP del cliente. Con proxy de confianza se usa la ultima IP de X-Forwarded-For
    (la que agrego nuestro proxy; las anteriores las puede inventar el cliente)."""
    if trust_proxy_headers:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                forwarded = [ip.strip() for ip in value.decode("latin-1").split(",") if ip.strip()]
                if forwarded:
                    return forwarded[-1]
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _send_json(send: Send, status: int, detail: str, extra_headers: list[tuple[bytes, bytes]] = ()) -> None:
    body = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        authenticated = any(name == b"authorization" for name, _ in scope.get("headers", []))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"server"]
                present = {k.lower() for k, _ in headers}

                def add(name: bytes, value: bytes) -> None:
                    if name not in present:
                        headers.append((name, value))

                add(b"x-content-type-options", b"nosniff")
                add(b"x-frame-options", b"DENY")
                add(b"referrer-policy", b"no-referrer")
                add(b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()")
                add(b"cross-origin-opener-policy", b"same-origin")
                if not path.startswith(_DOCS_PATHS):
                    add(b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
                if self.hsts:
                    add(b"strict-transport-security", b"max-age=63072000; includeSubDomains")
                if authenticated:
                    # Respuestas con datos privados: que ningun proxy ni navegador las guarde
                    add(b"cache-control", b"no-store")
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    too_large = int(value) > self.max_bytes
                except ValueError:
                    too_large = True
                if too_large:
                    await _send_json(send, 413, "La peticion es demasiado grande")
                    return

        # Sin Content-Length (chunked): se cuentan los bytes conforme llegan. Al pasarse
        # se responde 413 y la app ve al cliente desconectado (su respuesta se descarta).
        received = 0
        started = rejected = False

        async def limited_receive() -> Message:
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    rejected = True
                    if not started:
                        await _send_json(send, 413, "La peticion es demasiado grande")
                    return {"type": "http.disconnect"}
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if rejected:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except Exception:
            if not rejected:
                raise


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, per_minute: int, trust_proxy_headers: bool,
                 exempt_paths: tuple[str, ...] = ("/health",)) -> None:
        self.app = app
        self.limiter = SlidingWindowLimiter(per_minute, 60)
        self.trust_proxy_headers = trust_proxy_headers
        self.exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return
        ip = client_ip(scope, self.trust_proxy_headers)
        wait = self.limiter.check_and_hit(ip)
        if wait:
            logger.warning("Rate limit excedido ip=%s path=%s", ip, scope.get("path"))
            await _send_json(send, 429, "Demasiadas peticiones, intenta mas tarde",
                             [(b"retry-after", str(wait).encode())])
            return
        await self.app(scope, receive, send)
