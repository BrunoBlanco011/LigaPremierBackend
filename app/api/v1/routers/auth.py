from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CoachActor, CurrentActor, Teams, Users
from app.application.dto import LoginRequest
from app.domain.entities import Profile, Team

router = APIRouter(tags=["Auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: UUID


@router.post("/auth/login", response_model=TokenResponse, summary="Iniciar sesion (correo y contrasena)")
def login(data: LoginRequest, users: Users) -> TokenResponse:
    session = users.login(data)
    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        user_id=session.user_id,
    )


@router.get("/me", response_model=Profile, summary="Perfil del usuario autenticado")
def me(actor: CurrentActor, users: Users) -> Profile:
    return users.get(actor.id)


@router.get("/me/teams", response_model=list[Team], summary="Equipos asignados al coach autenticado")
def my_teams(actor: CoachActor, teams: Teams) -> list[Team]:
    return teams.list_by_coach(actor.id)
