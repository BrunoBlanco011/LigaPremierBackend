from __future__ import annotations

from uuid import UUID

from app.application.actor import Actor
from app.application.dto import LoginRequest, UserCreate, UserUpdate
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.domain.entities import Profile
from app.domain.enums import UserRole
from app.domain.repositories import AuthProvider, AuthSession, Repositories


class UserService:
    def __init__(self, repos: Repositories, auth: AuthProvider) -> None:
        self.repos = repos
        self.auth = auth

    def login(self, data: LoginRequest) -> AuthSession:
        return self.auth.sign_in(data.email, data.password)

    def get(self, user_id: UUID) -> Profile:
        profile = self.repos.profiles.get(user_id)
        if profile is None:
            raise NotFoundError("Usuario", user_id)
        return profile

    def list(self, role: UserRole | None = None) -> list[Profile]:
        return self.repos.profiles.list(filters={"role": role} if role else None, order_by=["full_name"])

    def create(self, data: UserCreate) -> Profile:
        """Crea la cuenta en Supabase Auth; el trigger `handle_new_user` crea el perfil."""
        new_user = self.auth.create_user(data.email, data.password, data.full_name)
        try:
            profile = self.repos.profiles.update(new_user.id, {"role": data.role, "full_name": data.full_name})
            if profile is None:
                raise AppError("No se genero el perfil del usuario (revisa el trigger on_auth_user_created)")
        except Exception:
            self.auth.delete_user(new_user.id)
            raise
        return profile

    def update(self, actor: Actor, user_id: UUID, data: UserUpdate) -> Profile:
        profile = self.get(user_id)
        changes = data.changes()
        if actor.id == user_id and changes.get("role", profile.role) != profile.role:
            raise ValidationError("No puedes cambiar tu propio rol")
        if not changes:
            return profile
        return self.repos.profiles.update(user_id, changes) or profile

    def delete(self, actor: Actor, user_id: UUID) -> None:
        if actor.id == user_id:
            raise ValidationError("No puedes eliminar tu propia cuenta")
        self.get(user_id)
        self.auth.delete_user(user_id)  # el perfil se borra en cascada
