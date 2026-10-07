import logging
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import Clubs, CoachActor, CurrentActor, Users
from app.application.dto import LoginRequest
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, TooManyRequestsError
from app.core.middleware import client_ip
from app.domain.entities import Club, Profile

router = APIRouter(tags=["Auth"])
audit = logging.getLogger("app.audit")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: UUID


@router.post("/auth/login", response_model=TokenResponse, summary="Iniciar sesion (correo y contrasena)")
def login(data: LoginRequest, request: Request, users: Users) -> TokenResponse:
    throttle = request.app.state.login_throttle
    ip = client_ip(request.scope, get_settings().trust_proxy_headers)
    wait = throttle.retry_after(ip, data.email)
    if wait:
        audit.warning("login bloqueado ip=%s email=%s", ip, data.email)
        raise TooManyRequestsError("Demasiados intentos de inicio de sesion, intenta mas tarde", wait)
    try:
        session = users.login(data)
    except AuthenticationError:
        throttle.failed(ip, data.email)
        audit.warning("login fallido ip=%s email=%s", ip, data.email)
        raise
    throttle.succeeded(ip, data.email)
    audit.info("login exitoso ip=%s user=%s", ip, session.user_id)
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
