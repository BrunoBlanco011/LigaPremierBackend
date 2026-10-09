"""Reintentos ante cortes de conexion con Supabase, con el cliente real y una red simulada."""

from uuid import uuid4

import httpx
from supabase import ClientOptions, create_client

from app.core.exceptions import ServiceUnavailableError
from app.domain.entities import Club
from app.infrastructure.repositories import supabase_repository
from app.infrastructure.repositories.supabase_repository import SupabaseRepository

supabase_repository.RETRY_DELAY_SECONDS = 0  # sin esperas en los tests

CLUB = {"id": str(uuid4()), "name": "TOROS", "logo_url": None, "coach_user_id": None,
        "created_at": "2026-10-09T00:00:00Z", "updated_at": "2026-10-09T00:00:00Z"}


def _repo(failures: list[Exception]) -> tuple[SupabaseRepository[Club], list[str]]:
    """Cada peticion consume el siguiente error de `failures`; cuando se acaban, responde bien."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if failures:
            raise failures.pop(0)
        return httpx.Response(200 if request.method == "GET" else 201, json=[CLUB])

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.supabase.co/rest/v1")
    client = create_client("https://example.supabase.co", "test-key", options=ClientOptions(httpx_client=http))
    return SupabaseRepository(client, "clubs", Club), calls


def test_reads_retry_after_server_disconnected():
    repo, calls = _repo([httpx.RemoteProtocolError("Server disconnected")])
    assert [c.name for c in repo.list()] == ["TOROS"]
    assert calls == ["GET", "GET"]


def test_gives_up_with_503_after_retries():
    repo, calls = _repo([httpx.RemoteProtocolError("Server disconnected")] * 5)
    try:
        repo.list()
        raise AssertionError("debio fallar")
    except ServiceUnavailableError as exc:
        assert exc.status_code == 503
    assert len(calls) == 1 + supabase_repository.RETRIES


def test_insert_is_not_repeated_when_the_request_may_have_arrived():
    # Se corto a medio camino: no se sabe si se guardo, asi que no se repite (evita duplicados)
    repo, calls = _repo([httpx.RemoteProtocolError("Server disconnected")])
    try:
        repo.create({"name": "TOROS"})
        raise AssertionError("debio fallar")
    except ServiceUnavailableError:
        pass
    assert calls == ["POST"]


def test_insert_retries_when_the_request_never_left():
    repo, calls = _repo([httpx.ConnectError("sin red")])
    assert repo.create({"name": "TOROS"}).name == "TOROS"
    assert calls == ["POST", "POST"]
