import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from typing import Annotated  # noqa: E402
from uuid import UUID  # noqa: E402

from fastapi import Depends  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import deps  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.fakes import FakeAuth, FakeStorage, build_fake_repositories  # noqa: E402

_bearer = HTTPBearer(auto_error=False)


class Env:
    """App de FastAPI conectada a repositorios en memoria. Token de prueba: 'token-<user_id>'."""

    def __init__(self) -> None:
        self.repos = build_fake_repositories()
        self.storage = FakeStorage()
        self.auth = FakeAuth(self.repos.profiles)
        self.app = create_app()

        def fake_subject(
            credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
        ) -> UUID | None:
            return UUID(credentials.credentials.removeprefix("token-")) if credentials else None

        self.app.dependency_overrides[deps.get_repositories] = lambda: self.repos
        self.app.dependency_overrides[deps.get_file_storage] = lambda: self.storage
        self.app.dependency_overrides[deps.get_auth_provider] = lambda: self.auth
        self.app.dependency_overrides[deps.get_token_subject] = fake_subject
        self.client = TestClient(self.app)

        self.admin = self.repos.profiles.create({"email": "admin@liga.mx", "role": "admin", "full_name": "Admin"})
        self.coach = self.repos.profiles.create({"email": "coach@liga.mx", "role": "coach", "full_name": "Coach"})

    @staticmethod
    def headers(profile) -> dict[str, str]:
        return {"Authorization": f"Bearer token-{profile.id}"}

    @property
    def as_admin(self) -> dict[str, str]:
        return self.headers(self.admin)

    @property
    def as_coach(self) -> dict[str, str]:
        return self.headers(self.coach)

    # --------------------------------------------------------- atajos
    def tournament(self, **kw) -> dict:
        r = self.client.post("/api/v1/tournaments", json={"name": "Apertura 2026", **kw}, headers=self.as_admin)
        assert r.status_code == 201, r.text
        return r.json()

    def team(self, tournament_id: str, name: str, **kw) -> dict:
        r = self.client.post(f"/api/v1/tournaments/{tournament_id}/teams", json={"name": name, **kw},
                             headers=self.as_admin)
        assert r.status_code == 201, r.text
        return r.json()

    def match(self, tournament_id: str, home: str, away: str, **kw) -> dict:
        r = self.client.post(f"/api/v1/tournaments/{tournament_id}/matches",
                             json={"home_team_id": home, "away_team_id": away, **kw}, headers=self.as_admin)
        assert r.status_code == 201, r.text
        return r.json()
