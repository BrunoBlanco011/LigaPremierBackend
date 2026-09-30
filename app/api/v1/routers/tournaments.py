"""Torneos y todos los recursos anidados en un torneo."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AdminActor, Matches, Rounds, Schedule, Standings, Stats, Teams, Tournaments
from app.application.dto import (
    AdjustmentCreate,
    MatchCreate,
    RoundCreate,
    ScheduleGenerate,
    TeamCreate,
    TournamentCreate,
    TournamentUpdate,
)
from app.application.read_models import MatchView, PlayerTotalsView, ScheduleResult, StandingView
from app.application.services.stats import StatSortField
from app.domain.entities import Round, StandingAdjustment, Team, Tournament
from app.domain.enums import MatchStatus, TournamentStatus

router = APIRouter(prefix="/tournaments", tags=["Torneos"])


# ------------------------------------------------------------ CRUD torneos
@router.get("", response_model=list[Tournament])
def list_tournaments(service: Tournaments, status_filter: Annotated[TournamentStatus | None, Query(alias="status")] = None):
    return service.list(status_filter)


@router.post("", response_model=Tournament, status_code=status.HTTP_201_CREATED)
def create_tournament(data: TournamentCreate, _: AdminActor, service: Tournaments):
    return service.create(data)


@router.get("/{tournament_id}", response_model=Tournament)
def get_tournament(tournament_id: UUID, service: Tournaments):
    return service.get(tournament_id)


@router.patch("/{tournament_id}", response_model=Tournament)
def update_tournament(tournament_id: UUID, data: TournamentUpdate, _: AdminActor, service: Tournaments):
    return service.update(tournament_id, data)


@router.delete("/{tournament_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Eliminar torneo (borra en cascada equipos, jornadas, partidos y estadisticas)")
def delete_tournament(tournament_id: UUID, _: AdminActor, service: Tournaments):
    service.delete(tournament_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------ equipos
@router.get("/{tournament_id}/teams", response_model=list[Team], tags=["Equipos"])
def list_teams(tournament_id: UUID, service: Teams):
    return service.list_by_tournament(tournament_id)


@router.post("/{tournament_id}/teams", response_model=Team, status_code=status.HTTP_201_CREATED, tags=["Equipos"])
def create_team(tournament_id: UUID, data: TeamCreate, _: AdminActor, service: Teams):
    return service.create(tournament_id, data)


# ------------------------------------------------------------ jornadas
@router.get("/{tournament_id}/rounds", response_model=list[Round], tags=["Jornadas"])
def list_rounds(tournament_id: UUID, service: Rounds):
    return service.list_by_tournament(tournament_id)


@router.post("/{tournament_id}/rounds", response_model=Round, status_code=status.HTTP_201_CREATED, tags=["Jornadas"])
def create_round(tournament_id: UUID, data: RoundCreate, _: AdminActor, service: Rounds):
    return service.create(tournament_id, data)


@router.post("/{tournament_id}/schedule/generate", response_model=ScheduleResult,
             status_code=status.HTTP_201_CREATED, tags=["Jornadas"],
             summary="Generar rol de juegos todos contra todos (con BYE si los equipos son impares)")
def generate_schedule(tournament_id: UUID, data: ScheduleGenerate, _: AdminActor, service: Schedule):
    return service.generate(tournament_id, data)


# ------------------------------------------------------------ partidos
@router.get("/{tournament_id}/matches", response_model=list[MatchView], tags=["Partidos"])
def list_matches(
    tournament_id: UUID,
    service: Matches,
    round_id: UUID | None = None,
    team_id: UUID | None = None,
    status_filter: Annotated[MatchStatus | None, Query(alias="status")] = None,
):
    return service.list(tournament_id, round_id=round_id, team_id=team_id, status=status_filter)


@router.post("/{tournament_id}/matches", response_model=MatchView, status_code=status.HTTP_201_CREATED,
             tags=["Partidos"])
def create_match(tournament_id: UUID, data: MatchCreate, _: AdminActor, service: Matches):
    return service.create(tournament_id, data)


# ------------------------------------------------------------ tabla de posiciones
@router.get("/{tournament_id}/standings", response_model=list[StandingView], tags=["Tabla de posiciones"],
            summary="Tabla de posiciones calculada en tiempo real")
def get_standings(tournament_id: UUID, service: Standings):
    return service.get_standings(tournament_id)


@router.get("/{tournament_id}/standings/adjustments", response_model=list[StandingAdjustment],
            tags=["Tabla de posiciones"])
def list_adjustments(tournament_id: UUID, service: Standings):
    return service.list_adjustments(tournament_id)


@router.post("/{tournament_id}/standings/adjustments", response_model=StandingAdjustment,
             status_code=status.HTTP_201_CREATED, tags=["Tabla de posiciones"],
             summary="Ajuste manual de puntos (sancion, multa, bonificacion)")
def create_adjustment(tournament_id: UUID, data: AdjustmentCreate, _: AdminActor, service: Standings):
    return service.create_adjustment(tournament_id, data)


# ------------------------------------------------------------ estadisticas
@router.get("/{tournament_id}/player-stats", response_model=list[PlayerTotalsView], tags=["Estadisticas"],
            summary="Acumulado de estadisticas por jugador (lideres)")
def tournament_player_stats(
    tournament_id: UUID,
    service: Stats,
    team_id: UUID | None = None,
    sort_by: StatSortField = "touchdowns",
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
):
    return service.tournament_totals(tournament_id, team_id=team_id, sort_by=sort_by, limit=limit)
