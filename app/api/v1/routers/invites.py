"""Auto-registro por link de invitacion (publico, sin sesion)."""

from fastapi import APIRouter, status

from app.api.deps import Invites
from app.application.dto import PlayerCreate
from app.application.read_models import ClubInviteInfo
from app.domain.entities import Player

router = APIRouter(prefix="/invites", tags=["Invitaciones"])


@router.get("/{token}", response_model=ClubInviteInfo,
            summary="Datos del club de una invitacion valida")
def invite_info(token: str, service: Invites) -> ClubInviteInfo:
    return service.info(token)


@router.post("/{token}/players", response_model=Player, status_code=status.HTTP_201_CREATED,
             summary="Darse de alta en el club con el link de invitacion")
def redeem_invite(token: str, data: PlayerCreate, service: Invites) -> Player:
    return service.redeem(token, data)
