import logging
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import AdminActor, Users
from app.application.dto import UserCreate, UserUpdate
from app.domain.entities import Profile
from app.domain.enums import UserRole

router = APIRouter(prefix="/users", tags=["Usuarios (admin)"])
audit = logging.getLogger("app.audit")


@router.get("", response_model=list[Profile])
def list_users(_: AdminActor, users: Users, role: UserRole | None = None) -> list[Profile]:
    return users.list(role)


@router.post("", response_model=Profile, status_code=status.HTTP_201_CREATED,
             summary="Crear usuario (coach o admin)")
def create_user(data: UserCreate, actor: AdminActor, users: Users) -> Profile:
    profile = users.create(data)
    audit.info("usuarios: alta user=%s rol=%s por=%s", profile.id, profile.role.value, actor.id)
    return profile


@router.get("/{user_id}", response_model=Profile)
def get_user(user_id: UUID, _: AdminActor, users: Users) -> Profile:
    return users.get(user_id)


@router.patch("/{user_id}", response_model=Profile)
def update_user(user_id: UUID, data: UserUpdate, actor: AdminActor, users: Users) -> Profile:
    profile = users.update(actor, user_id, data)
    audit.info("usuarios: cambio user=%s campos=%s por=%s", user_id, sorted(data.changes()), actor.id)
    return profile


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, actor: AdminActor, users: Users) -> Response:
    users.delete(actor, user_id)
    audit.info("usuarios: baja user=%s por=%s", user_id, actor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
