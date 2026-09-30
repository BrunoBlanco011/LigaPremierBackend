from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import AdminActor, Matches, Rounds, Standings, Stats
from app.application.dto import AdjustmentUpdate, MatchResult, MatchUpdate, PlayerStatLine, RoundUpdate
from app.application.read_models import MatchView, PlayerStatsDetail
from app.domain.entities import PlayerMatchStats, Round, StandingAdjustment

router = APIRouter()


# ------------------------------------------------------------ jornadas
@router.get("/rounds/{round_id}", response_model=Round, tags=["Jornadas"])
def get_round(round_id: UUID, service: Rounds):
    return service.get(round_id)


@router.patch("/rounds/{round_id}", response_model=Round, tags=["Jornadas"])
def update_round(round_id: UUID, data: RoundUpdate, _: AdminActor, service: Rounds):
    return service.update(round_id, data)


@router.delete("/rounds/{round_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Jornadas"],
               summary="Eliminar jornada (sus partidos se conservan sin jornada)")
def delete_round(round_id: UUID, _: AdminActor, service: Rounds):
    service.delete(round_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------ partidos
@router.get("/matches/{match_id}", response_model=MatchView, tags=["Partidos"])
def get_match(match_id: UUID, service: Matches):
    return service.get_view(match_id)


@router.patch("/matches/{match_id}", response_model=MatchView, tags=["Partidos"])
def update_match(match_id: UUID, data: MatchUpdate, _: AdminActor, service: Matches):
    return service.update(match_id, data)


@router.put("/matches/{match_id}/result", response_model=MatchView, tags=["Partidos"],
            summary="Capturar o corregir el resultado (actualiza la tabla automaticamente)")
def set_match_result(match_id: UUID, data: MatchResult, _: AdminActor, service: Matches):
    return service.set_result(match_id, data)


@router.delete("/matches/{match_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Partidos"])
def delete_match(match_id: UUID, _: AdminActor, service: Matches):
    service.delete(match_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------ estadisticas por partido
@router.get("/matches/{match_id}/stats", response_model=list[PlayerMatchStats], tags=["Estadisticas"])
def list_match_stats(match_id: UUID, service: Stats):
    return service.list_match_stats(match_id)


@router.put("/matches/{match_id}/stats", response_model=list[PlayerMatchStats], tags=["Estadisticas"],
            summary="Capturar estadisticas de jugadores (crea o reemplaza por jugador)")
def save_match_stats(match_id: UUID, lines: list[PlayerStatLine], _: AdminActor, service: Stats):
    return service.save_match_stats(match_id, lines)


@router.delete("/matches/{match_id}/stats/{player_id}", status_code=status.HTTP_204_NO_CONTENT,
               tags=["Estadisticas"])
def delete_match_stat(match_id: UUID, player_id: UUID, _: AdminActor, service: Stats):
    service.delete_match_stat(match_id, player_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/players/{player_id}/stats", response_model=PlayerStatsDetail, tags=["Estadisticas"])
def player_stats(player_id: UUID, service: Stats):
    return service.player_detail(player_id)


# ------------------------------------------------------------ ajustes de tabla
@router.patch("/standing-adjustments/{adjustment_id}", response_model=StandingAdjustment,
              tags=["Tabla de posiciones"])
def update_adjustment(adjustment_id: UUID, data: AdjustmentUpdate, _: AdminActor, service: Standings):
    return service.update_adjustment(adjustment_id, data)


@router.delete("/standing-adjustments/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT,
               tags=["Tabla de posiciones"])
def delete_adjustment(adjustment_id: UUID, _: AdminActor, service: Standings):
    service.delete_adjustment(adjustment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
