from dataclasses import dataclass
from uuid import UUID

from app.domain.enums import UserRole


@dataclass(frozen=True)
class Actor:
    """Usuario autenticado que ejecuta un caso de uso."""

    id: UUID
    role: UserRole
    email: str | None = None
    full_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
