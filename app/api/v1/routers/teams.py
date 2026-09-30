from uuid import UUID

from fastapi import APIRouter, File, Response, UploadFile, status

from app.api.deps import AdminActor, CurrentActor, OptionalActor, Players, Teams
from app.application.dto import PlayerCreate, PlayerUpdate, TeamUpdate
from app.domain.entities import Player, Team

router = APIRouter(tags=["Equipos"])


@router.get("/teams/{team_id}", response_model=Team)
def get_team(team_id: UUID, service: Teams):
    return service.get(team_id)


@router.patch("/teams/{team_id}", response_model=Team)
def update_team(team_id: UUID, data: TeamUpdate, _: AdminActor, service: Teams):
    return service.update(team_id, data)


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: UUID, _: AdminActor, service: Teams):
    service.delete(team_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/teams/{team_id}/logo", response_model=Team, summary="Subir/reemplazar el logo (png, jpg, webp, svg)")
def upload_logo(team_id: UUID, _: AdminActor, service: Teams, file: UploadFile = File(...)):
    # Endpoint sincrono: FastAPI lo corre en un threadpool y la subida a Storage no bloquea el event loop
    content = file.file.read(service.max_logo_bytes + 1)
    return service.upload_logo(team_id, content, file.content_type, file.filename)


# ------------------------------------------------------------ jugadores
@router.get("/teams/{team_id}/players", response_model=list[Player], tags=["Jugadores"],
            summary="Roster del equipo (datos personales solo para admin y su coach)")
def list_players(team_id: UUID, actor: OptionalActor, service: Players):
    return service.list_visible(actor, team_id)


@router.post("/teams/{team_id}/players", response_model=Player, status_code=status.HTTP_201_CREATED,
             tags=["Jugadores"], summary="Agregar jugador (admin o coach del equipo)")
def create_player(team_id: UUID, data: PlayerCreate, actor: CurrentActor, service: Players):
    return service.create(actor, team_id, data)


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
