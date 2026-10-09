import os

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.realtime import build_change_event
from tests.helpers import Env

API = "/api/v1"


def test_ws_receives_change_when_admin_writes():
    env = Env()
    t = env.tournament()
    with env.client.websocket_connect(f"{API}/ws") as ws:
        assert ws.receive_json() == {"type": "hello"}

        r = env.client.patch(f"{API}/tournaments/{t['id']}", json={"status": "active"}, headers=env.as_admin)
        assert r.status_code == 200
        event = ws.receive_json()
        assert event == {"type": "change", "resource": "tournaments", "action": "updated", "id": t["id"],
                         "tournament_id": t["id"], "path": f"{API}/tournaments/{t['id']}"}

        # Peticiones rechazadas no generan eventos: lo siguiente que llega es el pong
        assert env.client.post(f"{API}/tournaments", json={"name": "X"}).status_code == 401
        ws.send_text("ping")
        assert ws.receive_json() == {"type": "pong"}


def test_ws_skips_private_resources():
    env = Env()
    t = env.tournament()
    team = env.team(t["id"], "TOROS")
    with env.client.websocket_connect(f"{API}/ws") as ws:
        ws.receive_json()
        r = env.client.post(f"{API}/tournaments/{t['id']}/finance/movements",
                            json={"team_id": team["id"], "type": "fine", "amount": "500"}, headers=env.as_admin)
        assert r.status_code == 201, r.text
        ws.send_text("ping")
        assert ws.receive_json() == {"type": "pong"}


def test_change_event_shapes():
    assert build_change_event("POST", f"{API}/tournaments/abc/matches", API) == {
        "type": "change", "resource": "matches", "action": "created", "id": None,
        "tournament_id": "abc", "path": f"{API}/tournaments/abc/matches"}
    assert build_change_event("PUT", f"{API}/matches/m1/result", API)["id"] == "m1"
    assert build_change_event("DELETE", f"{API}/players/p1", API)["action"] == "deleted"
    assert build_change_event("GET", f"{API}/matches/m1", API) is None
    assert build_change_event("POST", f"{API}/auth/login", API) is None
    assert build_change_event("PATCH", f"{API}/users/u1", API) is None
    assert build_change_event("PATCH", f"{API}/finance/movements/x", API) is None
    assert build_change_event("POST", f"{API}/invites/secreto/players", API) is None
    assert build_change_event("POST", f"{API}/clubs/c1/invites", API) is None


def test_ws_rejects_foreign_origin_and_limits_connections():
    os.environ.update(CORS_ORIGINS="http://localhost:5173", WS_MAX_CONNECTIONS_PER_IP="1")
    get_settings.cache_clear()
    try:
        env = Env()
        client = TestClient(env.app)
        try:
            with client.websocket_connect(f"{API}/ws", headers={"origin": "https://evil.example"}):
                raise AssertionError("debio rechazarse")
        except WebSocketDisconnect as exc:
            assert exc.code == 1008

        with client.websocket_connect(f"{API}/ws", headers={"origin": "http://localhost:5173"}) as ws:
            assert ws.receive_json() == {"type": "hello"}
            try:
                with client.websocket_connect(f"{API}/ws"):
                    raise AssertionError("debio rechazarse por limite de conexiones")
            except WebSocketDisconnect as exc:
                assert exc.code == 1013
        assert env.app.state.realtime.connections == 0
    finally:
        del os.environ["CORS_ORIGINS"], os.environ["WS_MAX_CONNECTIONS_PER_IP"]
        get_settings.cache_clear()
