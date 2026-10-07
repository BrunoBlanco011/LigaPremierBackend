from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import BodySizeLimitMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import LoginThrottle, SlidingWindowLimiter
from tests.helpers import Env
from tests.test_api import PNG

API = "/api/v1"
_MIDDLEWARES = {"body": BodySizeLimitMiddleware, "rate": RateLimitMiddleware, "headers": SecurityHeadersMiddleware}


def _mini_app(**middlewares) -> TestClient:
    app = FastAPI()

    @app.post("/echo")
    async def echo(payload: dict) -> dict:
        return payload

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    for name, kwargs in middlewares.items():
        app.add_middleware(_MIDDLEWARES[name], **kwargs)
    return TestClient(app)


# ------------------------------------------------------------ cabeceras
def test_security_headers_on_every_response():
    env = Env()
    r = env.client.get(f"{API}/tournaments")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "cache-control" not in r.headers  # datos publicos: se pueden cachear

    r = env.client.get(f"{API}/me", headers=env.as_admin)
    assert r.headers["cache-control"] == "no-store"  # datos privados: nunca en cache
    # Los errores tambien llevan las cabeceras
    assert env.client.get(f"{API}/me").headers["x-frame-options"] == "DENY"


def test_hsts_only_when_enabled():
    assert "strict-transport-security" not in _mini_app(headers={"hsts": False}).get("/ping").headers
    assert "max-age" in _mini_app(headers={"hsts": True}).get("/ping").headers["strict-transport-security"]


def test_unexpected_errors_do_not_leak_details():
    env = Env()

    @env.app.get("/boom")
    def boom():
        raise RuntimeError("password=supersecreto en la base")

    client = TestClient(env.app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500 and r.json() == {"detail": "Error interno del servidor"}
    assert "supersecreto" not in r.text


# ------------------------------------------------------------ tamano y rate limit
def test_body_size_limit():
    client = _mini_app(body={"max_bytes": 100})
    assert client.post("/echo", json={"a": "x" * 10}).status_code == 200
    assert client.post("/echo", json={"a": "x" * 500}).status_code == 413

    def chunks():  # sin Content-Length
        yield b'{"a": "' + b"x" * 200 + b'"}'

    assert client.post("/echo", content=chunks(), headers={"content-type": "application/json"}).status_code == 413


def test_global_rate_limit_per_ip():
    client = _mini_app(rate={"per_minute": 3, "trust_proxy_headers": False})
    assert [client.get("/ping").status_code for _ in range(3)] == [200, 200, 200]
    r = client.get("/ping")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_forwarded_ip_only_used_behind_trusted_proxy():
    client = _mini_app(rate={"per_minute": 1, "trust_proxy_headers": True})
    assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
    # El cliente no puede evadir el limite poniendo IPs falsas al inicio de la cadena
    assert client.get("/ping", headers={"X-Forwarded-For": "9.9.9.9, 2.2.2.2"}).status_code == 429


def test_sliding_window_limiter_and_login_throttle():
    limiter = SlidingWindowLimiter(2, 60)
    assert limiter.check_and_hit("a") == 0 and limiter.check_and_hit("a") == 0
    assert limiter.check_and_hit("a") > 0 and limiter.check_and_hit("b") == 0
    limiter.reset("a")
    assert limiter.retry_after("a") == 0

    throttle = LoginThrottle(max_attempts=2, window_seconds=60)
    for email in ("a@x.mx", "b@x.mx", "c@x.mx", "d@x.mx"):
        throttle.failed("1.1.1.1", email)
        throttle.failed("1.1.1.1", email)
    assert throttle.retry_after("1.1.1.1", "nuevo@x.mx") > 0  # spraying desde la misma IP
    assert throttle.retry_after("2.2.2.2", "a@x.mx") == 0


# ------------------------------------------------------------ login
def test_login_brute_force_is_blocked():
    env = Env()
    env.client.post(f"{API}/users", json={"email": "nuevo@liga.mx", "password": "Secreto2026"}, headers=env.as_admin)
    bad = {"email": "nuevo@liga.mx", "password": "incorrecta"}
    codes = [env.client.post(f"{API}/auth/login", json=bad).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    # Ni con la contrasena correcta mientras dure el bloqueo
    r = env.client.post(f"{API}/auth/login", json={**bad, "password": "Secreto2026"})
    assert r.status_code == 429 and "retry-after" in r.headers


def test_successful_login_resets_failed_attempts():
    env = Env()
    env.client.post(f"{API}/users", json={"email": "nuevo@liga.mx", "password": "Secreto2026"}, headers=env.as_admin)
    good = {"email": "nuevo@liga.mx", "password": "Secreto2026"}
    for _ in range(4):
        env.client.post(f"{API}/auth/login", json={**good, "password": "incorrecta"})
    assert env.client.post(f"{API}/auth/login", json=good).status_code == 200
    for _ in range(4):
        assert env.client.post(f"{API}/auth/login", json={**good, "password": "incorrecta"}).status_code == 401


# ------------------------------------------------------------ contrasenas
def test_password_policy():
    env = Env()
    url = f"{API}/users"
    for password in ("corta1", "solotextolargo", "1234567890", "nuevo2026abc"):  # la ultima contiene el correo
        r = env.client.post(url, json={"email": "nuevo@liga.mx", "password": password}, headers=env.as_admin)
        assert r.status_code == 422, password
    r = env.client.post(url, json={"email": "nuevo@liga.mx", "password": "Tocho-Bandera-26"}, headers=env.as_admin)
    assert r.status_code == 201


# ------------------------------------------------------------ logos
def test_logo_content_is_verified():
    env = Env()
    club = env.club("TOROS")
    url = f"{API}/clubs/{club['id']}/logo"

    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert env.client.post(url, files={"file": ("x.svg", svg, "image/svg+xml")}, headers=env.as_admin).status_code == 422
    # HTML disfrazado de PNG
    fake = {"file": ("logo.png", b"<html><script>alert(1)</script></html>", "image/png")}
    assert env.client.post(url, files=fake, headers=env.as_admin).status_code == 422
    # La extension la decide el servidor, no el nombre del archivo
    r = env.client.post(url, files={"file": ("logo.html", PNG, "image/png")}, headers=env.as_admin)
    assert r.status_code == 200 and r.json()["logo_path"].endswith(".png")
