from __future__ import annotations

from uuid import UUID, uuid4

from app.application.actor import Actor
from app.application.dto import ClubCreate, ClubUpdate
from app.application.read_models import ClubSeason
from app.application.services.standings import StandingsService
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.domain.entities import Club
from app.domain.enums import UserRole
from app.domain.repositories import FileStorage, Repositories

# SVG no se acepta: puede contener JavaScript y se sirve desde un bucket publico (XSS)
ALLOWED_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def detect_image_type(content: bytes) -> str | None:
    """Tipo real del archivo segun sus primeros bytes (no se confia en el content-type del cliente)."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


class ClubService:
    """Clubes: equipos permanentes de la liga que se inscriben a los torneos."""

    def __init__(self, repos: Repositories, storage: FileStorage, max_logo_bytes: int) -> None:
        self.repos = repos
        self.storage = storage
        self.max_logo_bytes = max_logo_bytes

    def list(self) -> list[Club]:
        return self.repos.clubs.list(order_by=["name"])

    def list_by_coach(self, coach_user_id: UUID) -> list[Club]:
        return self.repos.clubs.list(filters={"coach_user_id": coach_user_id}, order_by=["name"])

    def get(self, club_id: UUID) -> Club:
        club = self.repos.clubs.get(club_id)
        if club is None:
            raise NotFoundError("Club", club_id)
        return club

    def create(self, data: ClubCreate) -> Club:
        self._ensure_unique_name(data.name)
        if data.coach_user_id:
            self._ensure_coach(data.coach_user_id)
        return self.repos.clubs.create(data.model_dump())

    def update(self, actor: Actor, club_id: UUID, data: ClubUpdate) -> Club:
        club = self.get(club_id)
        self._ensure_can_manage(actor, club)
        changes = data.changes()
        # Solo el admin puede reasignar el coach de un club.
        if not actor.is_admin and "coach_user_id" in changes:
            raise PermissionDeniedError("Solo el administrador puede reasignar el coach del club")
        if "name" in changes and changes["name"].lower() != club.name.lower():
            self._ensure_unique_name(changes["name"])
        if changes.get("coach_user_id"):
            self._ensure_coach(changes["coach_user_id"])
        if not changes:
            return club
        return self.repos.clubs.update(club_id, changes) or club

    def delete(self, club_id: UUID) -> None:
        """Solo se puede borrar un club sin torneos jugados: su historial se conserva."""
        club = self.get(club_id)
        if self.repos.teams.list(filters={"club_id": club_id}):
            raise ConflictError("El club esta inscrito en uno o mas torneos; no se puede eliminar")
        self.repos.clubs.delete(club_id)
        if club.logo_path:
            self.storage.delete(club.logo_path)

    def upload_logo(self, actor: Actor, club_id: UUID, content: bytes, content_type: str | None) -> Club:
        club = self.get(club_id)
        self._ensure_can_manage(actor, club)
        if content_type not in ALLOWED_LOGO_TYPES:
            raise ValidationError(f"Formato no permitido. Usa: {', '.join(ALLOWED_LOGO_TYPES)}")
        if not content:
            raise ValidationError("El archivo esta vacio")
        if len(content) > self.max_logo_bytes:
            raise ValidationError(f"El logo excede {self.max_logo_bytes // (1024 * 1024)} MB")
        if detect_image_type(content) != content_type:
            raise ValidationError("El contenido del archivo no corresponde a una imagen valida")

        # La extension sale del tipo verificado, nunca del nombre que manda el cliente
        extension = ALLOWED_LOGO_TYPES[content_type]
        # Nombre unico por subida: evita que el CDN sirva el logo anterior desde cache
        path = f"clubs/{club.id}/{uuid4().hex}{extension}"
        url = self.storage.upload(path, content, content_type)
        updated = self.repos.clubs.update(club_id, {"logo_url": url, "logo_path": path}) or club
        if club.logo_path:
            self.storage.delete(club.logo_path)
        return updated

    def history(self, club_id: UUID) -> list[ClubSeason]:
        """Torneos en los que participo el club y su posicion en cada uno."""
        self.get(club_id)
        teams = self.repos.teams.list(filters={"club_id": club_id})
        if not teams:
            return []
        tournaments = {t.id: t for t in self.repos.tournaments.list(in_filters={"id": [t.tournament_id for t in teams]})}
        standings = StandingsService(self.repos)
        seasons = []
        for team in teams:
            tournament = tournaments.get(team.tournament_id)
            if tournament is None:
                continue
            table = standings.get_standings(tournament.id)
            row = next((r for r in table if r.team.id == team.id), None)
            seasons.append(ClubSeason(tournament=tournament, team_id=team.id, standing=row, teams_count=len(table)))
        seasons.sort(key=lambda s: (s.tournament.start_date is None, s.tournament.start_date), reverse=True)
        return seasons

    @staticmethod
    def can_manage(actor: Actor | None, club: Club) -> bool:
        """Admin gestiona cualquier club; un coach solo el suyo."""
        return actor is not None and (actor.is_admin or club.coach_user_id == actor.id)

    def _ensure_can_manage(self, actor: Actor, club: Club) -> None:
        if not self.can_manage(actor, club):
            raise PermissionDeniedError("Solo puedes administrar tu propio club")

    def _ensure_unique_name(self, name: str) -> None:
        if any(c.name.strip().lower() == name.strip().lower() for c in self.repos.clubs.list()):
            raise ConflictError(f"Ya existe un club llamado '{name}'")

    def _ensure_coach(self, user_id: UUID) -> None:
        profile = self.repos.profiles.get(user_id)
        if profile is None:
            raise ValidationError("El usuario coach no existe")
        if profile.role != UserRole.COACH:
            raise ValidationError("El usuario asignado debe tener rol 'coach'")
