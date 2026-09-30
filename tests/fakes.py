"""Implementaciones en memoria de los puertos: permiten probar sin Supabase."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.core.exceptions import AuthenticationError
from app.domain.entities import (
    Club,
    FinanceMovement,
    Match,
    Player,
    PlayerMatchStats,
    Profile,
    Round,
    StandingAdjustment,
    Team,
    Tournament,
)
from app.domain.repositories import AuthSession, NewAuthUser, Repositories

T = TypeVar("T", bound=BaseModel)


def _norm(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    return value


class InMemoryRepository(Generic[T]):
    def __init__(self, model: type[T]) -> None:
        self.model = model
        self.rows: dict[UUID, T] = {}

    def _view(self, entity: T) -> T:
        """Gancho para simular vistas de lectura (ver TeamDetailsRepository)."""
        return entity

    def get(self, entity_id: UUID) -> T | None:
        entity = self.rows.get(UUID(str(entity_id)))
        return self._view(entity) if entity is not None else None

    def list(self, *, filters=None, in_filters=None, order_by: Sequence[str] = ()) -> list[T]:
        result = [self._view(r) for r in self.rows.values()]
        for col, value in (filters or {}).items():
            result = [r for r in result if _norm(getattr(r, col)) == _norm(value)]
        for col, values in (in_filters or {}).items():
            allowed = {_norm(v) for v in values}
            result = [r for r in result if _norm(getattr(r, col)) in allowed]
        for col in reversed(order_by):
            key = col.lstrip("-")
            nones = [r for r in result if getattr(r, key) is None]
            vals = sorted((r for r in result if getattr(r, key) is not None),
                          key=lambda r: getattr(r, key), reverse=col.startswith("-"))
            result = vals + nones
        return result

    def create(self, data: Mapping[str, Any]) -> T:
        now = datetime.now(timezone.utc)
        entity = self.model.model_validate({"id": uuid4(), "created_at": now, "updated_at": now, **data})
        self.rows[entity.id] = entity
        return self._view(entity)

    def create_many(self, rows: Sequence[Mapping[str, Any]]) -> list[T]:
        return [self.create(r) for r in rows]

    def update(self, entity_id: UUID, data: Mapping[str, Any]) -> T | None:
        current = self.rows.get(UUID(str(entity_id)))
        if current is None:
            return None
        updated = self.model.model_validate({**current.model_dump(), **data})
        self.rows[updated.id] = updated
        return self._view(updated)

    def delete(self, entity_id: UUID) -> bool:
        return self.rows.pop(UUID(str(entity_id)), None) is not None

    def upsert_many(self, rows: Sequence[Mapping[str, Any]], on_conflict: Sequence[str]) -> list[T]:
        out = []
        for row in rows:
            existing = self.list(filters={c: row[c] for c in on_conflict})
            out.append(self.update(existing[0].id, row) if existing else self.create(row))
        return out


class TeamDetailsRepository(InMemoryRepository[Team]):
    """Simula la vista `team_details`: la inscripcion muestra nombre, logo y coach de su club."""

    def __init__(self, clubs: InMemoryRepository[Club]) -> None:
        super().__init__(Team)
        self.clubs = clubs

    def _view(self, entity: Team) -> Team:
        club = self.clubs.get(entity.club_id)
        if club is None:
            return entity
        return entity.model_copy(update={
            "name": club.name, "logo_url": club.logo_url,
            "coach_name": club.coach_name, "coach_user_id": club.coach_user_id,
        })


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def upload(self, path: str, content: bytes, content_type: str) -> str:
        self.files[path] = content
        return f"https://cdn.test/{path}"

    def delete(self, path: str) -> None:
        self.files.pop(path, None)


class FakeAuth:
    def __init__(self, profiles: InMemoryRepository[Profile]) -> None:
        self.profiles = profiles
        self.passwords: dict[str, tuple[UUID, str]] = {}

    def create_user(self, email: str, password: str, full_name: str | None) -> NewAuthUser:
        # Simula el trigger handle_new_user
        profile = self.profiles.create({"email": email, "full_name": full_name, "role": "coach"})
        self.passwords[email] = (profile.id, password)
        return NewAuthUser(id=profile.id, email=email)

    def delete_user(self, user_id: UUID) -> None:
        self.profiles.delete(user_id)

    def sign_in(self, email: str, password: str) -> AuthSession:
        user_id, stored = self.passwords.get(email, (None, None))
        if user_id is None or stored != password:
            raise AuthenticationError("Correo o contrasena incorrectos")
        return AuthSession(access_token=f"token-{user_id}", refresh_token="r", expires_in=3600, user_id=user_id)


def build_fake_repositories() -> Repositories:
    clubs = InMemoryRepository(Club)
    return Repositories(
        profiles=InMemoryRepository(Profile),
        tournaments=InMemoryRepository(Tournament),
        clubs=clubs,
        teams=TeamDetailsRepository(clubs),
        players=InMemoryRepository(Player),
        rounds=InMemoryRepository(Round),
        matches=InMemoryRepository(Match),
        adjustments=InMemoryRepository(StandingAdjustment),
        player_stats=InMemoryRepository(PlayerMatchStats),
        finance=InMemoryRepository(FinanceMovement),
    )
