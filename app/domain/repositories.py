"""Puertos (interfaces) que la capa de aplicacion necesita.

La infraestructura (Supabase) los implementa; los tests usan versiones en
memoria. Cambiar de base de datos solo requiere una nueva implementacion.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar
from uuid import UUID

from app.domain.entities import (
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

T = TypeVar("T")


class Repository(Protocol, Generic[T]):
    def get(self, entity_id: UUID) -> T | None: ...

    def list(
        self,
        *,
        filters: Mapping[str, Any] | None = None,
        in_filters: Mapping[str, Sequence[Any]] | None = None,
        order_by: Sequence[str] = (),
    ) -> list[T]:
        """`filters`: igualdad exacta. `in_filters`: columna IN (...). `order_by`: '-col' = descendente."""
        ...

    def create(self, data: Mapping[str, Any]) -> T: ...

    def create_many(self, rows: Sequence[Mapping[str, Any]]) -> list[T]: ...

    def update(self, entity_id: UUID, data: Mapping[str, Any]) -> T | None: ...

    def delete(self, entity_id: UUID) -> bool: ...

    def upsert_many(self, rows: Sequence[Mapping[str, Any]], on_conflict: Sequence[str]) -> list[T]: ...


class FileStorage(Protocol):
    def upload(self, path: str, content: bytes, content_type: str) -> str:
        """Sube el archivo y devuelve su URL publica."""
        ...

    def delete(self, path: str) -> None: ...


@dataclass(frozen=True)
class NewAuthUser:
    id: UUID
    email: str


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: UUID


class AuthProvider(Protocol):
    def create_user(self, email: str, password: str, full_name: str | None) -> NewAuthUser: ...

    def delete_user(self, user_id: UUID) -> None: ...

    def sign_in(self, email: str, password: str) -> AuthSession: ...


@dataclass(frozen=True)
class Repositories:
    """Agrupa todos los repositorios para inyectarlos en los servicios."""

    profiles: Repository[Profile]
    tournaments: Repository[Tournament]
    teams: Repository[Team]
    players: Repository[Player]
    rounds: Repository[Round]
    matches: Repository[Match]
    adjustments: Repository[StandingAdjustment]
    player_stats: Repository[PlayerMatchStats]
    finance: Repository[FinanceMovement]
