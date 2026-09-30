from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import Clubs, CoachActor, CurrentActor, Users
from app.application.dto import LoginRequest
from app.domain.entities import Club, Profile

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


@router.get("/me/clubs", response_model=list[Club], summary="Clubes asignados al coach autenticado")
def my_clubs(actor: CoachActor, clubs: Clubs) -> list[Club]:
    return clubs.list_by_coach(actor.id)
