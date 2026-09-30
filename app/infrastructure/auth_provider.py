from uuid import UUID

from supabase import AuthApiError, AuthError, Client

from app.core.exceptions import AuthenticationError, ConflictError, ValidationError
from app.domain.repositories import AuthSession, NewAuthUser
from app.infrastructure.supabase_client import new_anon_client


class SupabaseAuthProvider:
    def __init__(self, service_client: Client) -> None:
        self.client = service_client

    def create_user(self, email: str, password: str, full_name: str | None) -> NewAuthUser:
        try:
            response = self.client.auth.admin.create_user(
                {
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"full_name": full_name} if full_name else {},
                }
            )
        except AuthApiError as exc:
            if exc.status == 422 or "already" in exc.message.lower():
                raise ConflictError("Ya existe un usuario con ese correo") from exc
            raise ValidationError(exc.message) from exc
        return NewAuthUser(id=UUID(response.user.id), email=email)

    def delete_user(self, user_id: UUID) -> None:
        self.client.auth.admin.delete_user(str(user_id))

    def sign_in(self, email: str, password: str) -> AuthSession:
        try:
            response = new_anon_client().auth.sign_in_with_password({"email": email, "password": password})
        except AuthError as exc:
            raise AuthenticationError("Correo o contrasena incorrectos") from exc
        session = response.session
        if session is None or response.user is None:
            raise AuthenticationError("Correo o contrasena incorrectos")
        return AuthSession(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_in=session.expires_in,
            user_id=UUID(response.user.id),
        )
