"""Inyeccion de dependencias: aqui se conectan las capas.

Los tests reemplazan `get_repositories`, `get_file_storage`, `get_auth_provider`
y `get_token_subject` con `app.dependency_overrides`.
"""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.actor import Actor
from app.application.services.finance import FinanceService
from app.application.services.matches import MatchService
from app.application.services.clubs import ClubService
from app.application.services.players import PlayerService
from app.application.services.rounds import RoundService
from app.application.services.schedule import ScheduleService
from app.application.services.standings import StandingsService
from app.application.services.stats import StatsService
from app.application.services.teams import TeamService
from app.application.services.tournaments import TournamentService
from app.application.services.users import UserService
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.domain.enums import UserRole
from app.domain.repositories import AuthProvider, FileStorage, Repositories

_bearer = HTTPBearer(auto_error=False, description="access_token de Supabase Auth")


# ------------------------------------------------------------ infraestructura
@lru_cache
def get_repositories() -> Repositories:
    from app.infrastructure.repositories import build_supabase_repositories
    from app.infrastructure.supabase_client import get_service_client

    return build_supabase_repositories(get_service_client())


@lru_cache
def get_file_storage() -> FileStorage:
    from app.infrastructure.storage import SupabaseFileStorage
    from app.infrastructure.supabase_client import get_service_client

    return SupabaseFileStorage(get_service_client(), get_settings().team_logos_bucket)


@lru_cache
def get_auth_provider() -> AuthProvider:
    from app.infrastructure.auth_provider import SupabaseAuthProvider
    from app.infrastructure.supabase_client import get_service_client

    return SupabaseAuthProvider(get_service_client())


Repos = Annotated[Repositories, Depends(get_repositories)]


# ------------------------------------------------------------ servicios
def get_tournament_service(repos: Repos) -> TournamentService:
    return TournamentService(repos)


def get_club_service(repos: Repos, storage: Annotated[FileStorage, Depends(get_file_storage)]) -> ClubService:
    return ClubService(repos, storage, get_settings().max_logo_size_mb * 1024 * 1024)


def get_team_service(repos: Repos) -> TeamService:
    return TeamService(repos)


def get_player_service(repos: Repos, clubs: Annotated[ClubService, Depends(get_club_service)]) -> PlayerService:
    return PlayerService(repos, clubs)


def get_round_service(repos: Repos) -> RoundService:
    return RoundService(repos)


def get_match_service(repos: Repos) -> MatchService:
    return MatchService(repos)


def get_schedule_service(repos: Repos) -> ScheduleService:
    return ScheduleService(repos)


def get_finance_service(repos: Repos) -> FinanceService:
    return FinanceService(repos)


def get_standings_service(repos: Repos) -> StandingsService:
    return StandingsService(repos)


def get_stats_service(repos: Repos) -> StatsService:
    return StatsService(repos)


def get_user_service(repos: Repos, auth: Annotated[AuthProvider, Depends(get_auth_provider)]) -> UserService:
    return UserService(repos, auth)


# ------------------------------------------------------------ autenticacion
def get_token_subject(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UUID | None:
    if credentials is None:
        return None
    return decode_access_token(credentials.credentials)


def get_optional_actor(repos: Repos, user_id: Annotated[UUID | None, Depends(get_token_subject)]) -> Actor | None:
    if user_id is None:
        return None
    profile = repos.profiles.get(user_id)
    if profile is None:
        raise PermissionDeniedError("El usuario no tiene perfil en la liga")
    return Actor(id=profile.id, role=profile.role, email=profile.email, full_name=profile.full_name)


def get_current_actor(actor: Annotated[Actor | None, Depends(get_optional_actor)]) -> Actor:
    if actor is None:
        raise AuthenticationError("Se requiere autenticacion")
    return actor


def require_admin(actor: Annotated[Actor, Depends(get_current_actor)]) -> Actor:
    if actor.role != UserRole.ADMIN:
        raise PermissionDeniedError("Se requiere rol de administrador")
    return actor


def require_coach(actor: Annotated[Actor, Depends(get_current_actor)]) -> Actor:
    if actor.role != UserRole.COACH:
        raise PermissionDeniedError("Se requiere rol de coach")
    return actor


OptionalActor = Annotated[Actor | None, Depends(get_optional_actor)]
CurrentActor = Annotated[Actor, Depends(get_current_actor)]
AdminActor = Annotated[Actor, Depends(require_admin)]
CoachActor = Annotated[Actor, Depends(require_coach)]

Tournaments = Annotated[TournamentService, Depends(get_tournament_service)]
Clubs = Annotated[ClubService, Depends(get_club_service)]
Teams = Annotated[TeamService, Depends(get_team_service)]
Players = Annotated[PlayerService, Depends(get_player_service)]
Rounds = Annotated[RoundService, Depends(get_round_service)]
Matches = Annotated[MatchService, Depends(get_match_service)]
Schedule = Annotated[ScheduleService, Depends(get_schedule_service)]
Finance = Annotated[FinanceService, Depends(get_finance_service)]
Standings = Annotated[StandingsService, Depends(get_standings_service)]
Stats = Annotated[StatsService, Depends(get_stats_service)]
Users = Annotated[UserService, Depends(get_user_service)]
