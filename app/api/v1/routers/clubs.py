from uuid import UUID

from fastapi import APIRouter, File, Response, UploadFile, status

from app.api.deps import AdminActor, Clubs, CurrentActor, Invites, OptionalActor, Players
from app.application.dto import ClubCreate, ClubUpdate, PlayerCreate
from app.application.read_models import ClubSeason
from app.domain.entities import Club, ClubInvite, Player

router = APIRouter(prefix="/clubs", tags=["Clubes"])


@router.get("", response_model=list[Club])
def list_clubs(service: Clubs):
    return service.list()


@router.post("", response_model=Club, status_code=status.HTTP_201_CREATED)
def create_club(data: ClubCreate, _: AdminActor, service: Clubs):
    return service.create(data)


@router.get("/{club_id}", response_model=Club)
def get_club(club_id: UUID, service: Clubs):
    return service.get(club_id)


@router.patch("/{club_id}", response_model=Club, summary="Editar club (admin, o el coach de ese club)")
def update_club(club_id: UUID, data: ClubUpdate, actor: CurrentActor, service: Clubs):
    return service.update(actor, club_id, data)


@router.delete("/{club_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Eliminar club (solo si nunca se ha inscrito a un torneo)")
def delete_club(club_id: UUID, _: AdminActor, service: Clubs):
    service.delete(club_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{club_id}/logo", response_model=Club,
             summary="Subir/reemplazar el logo (admin o coach del club · png, jpg, webp)")
def upload_logo(club_id: UUID, actor: CurrentActor, service: Clubs, file: UploadFile = File(...)):
    # Endpoint sincrono: FastAPI lo corre en un threadpool y la subida a Storage no bloquea el event loop
    content = file.file.read(service.max_logo_bytes + 1)
    return service.upload_logo(actor, club_id, content, file.content_type)


@router.post("/{club_id}/invites", response_model=ClubInvite, status_code=status.HTTP_201_CREATED,
             tags=["Invitaciones"],
             summary="Generar link de invitacion (24h) para que los jugadores se den de alta solos")
def create_invite(club_id: UUID, actor: CurrentActor, service: Invites):
    return service.create(actor, club_id)


@router.get("/{club_id}/history", response_model=list[ClubSeason],
            summary="Torneos en los que ha participado el club y su posicion final")
def club_history(club_id: UUID, service: Clubs):
    return service.history(club_id)


# ------------------------------------------------------------ jugadores
@router.get("/{club_id}/players", response_model=list[Player], tags=["Jugadores"],
            summary="Plantilla del club (las bajas solo las ven el admin y su coach)")
def list_players(club_id: UUID, actor: OptionalActor, service: Players):
    return service.list_visible(actor, club_id)


@router.post("/{club_id}/players", response_model=Player, status_code=status.HTTP_201_CREATED,
             tags=["Jugadores"], summary="Agregar jugador (admin o coach del club)")
def create_player(club_id: UUID, data: PlayerCreate, actor: CurrentActor, service: Players):
    return service.create(actor, club_id, data)
