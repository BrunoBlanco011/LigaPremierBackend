from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import AdminActor, CurrentActor, OptionalActor, Players, Teams
from app.application.dto import PlayerUpdate
from app.domain.entities import Player, Team

router = APIRouter(tags=["Equipos (inscripciones)"])


@router.get("/teams/{team_id}", response_model=Team)
def get_team(team_id: UUID, service: Teams):
    return service.get(team_id)


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Dar de baja al club del torneo (borra sus partidos, estadisticas y finanzas del torneo)")
def unregister_team(team_id: UUID, _: AdminActor, service: Teams):
    service.unregister(team_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/teams/{team_id}/players", response_model=list[Player], tags=["Jugadores"],
            summary="Plantilla del club de esta inscripcion")
def list_team_players(team_id: UUID, actor: OptionalActor, teams: Teams, players: Players):
    return players.list_visible(actor, teams.get(team_id).club_id)


# ------------------------------------------------------------ jugadores
@router.get("/players/{player_id}", response_model=Player, tags=["Jugadores"])
def get_player(player_id: UUID, actor: OptionalActor, service: Players):
    return service.get_visible(actor, player_id)


@router.patch("/players/{player_id}", response_model=Player, tags=["Jugadores"])
def update_player(player_id: UUID, data: PlayerUpdate, actor: CurrentActor, service: Players):
    return service.update(actor, player_id, data)


@router.delete("/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Jugadores"])
def delete_player(player_id: UUID, actor: CurrentActor, service: Players):
    service.delete(actor, player_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
