from pathlib import PurePath
from uuid import UUID, uuid4

from app.application.dto import TeamCreate, TeamUpdate
from app.application.services.tournaments import TournamentService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.entities import Team
from app.domain.enums import UserRole
from app.domain.repositories import FileStorage, Repositories

ALLOWED_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/svg+xml": ".svg"}


class TeamService:
    def __init__(self, repos: Repositories, storage: FileStorage, max_logo_bytes: int) -> None:
        self.repos = repos
        self.storage = storage
        self.max_logo_bytes = max_logo_bytes
        self.tournaments = TournamentService(repos)

    def list_by_tournament(self, tournament_id: UUID) -> list[Team]:
        self.tournaments.get(tournament_id)
        return self.repos.teams.list(filters={"tournament_id": tournament_id}, order_by=["name"])

    def list_by_coach(self, coach_user_id: UUID) -> list[Team]:
        return self.repos.teams.list(filters={"coach_user_id": coach_user_id}, order_by=["name"])

    def get(self, team_id: UUID) -> Team:
        team = self.repos.teams.get(team_id)
        if team is None:
            raise NotFoundError("Equipo", team_id)
        return team

    def create(self, tournament_id: UUID, data: TeamCreate) -> Team:
        self.tournaments.get(tournament_id)
        self._ensure_unique_name(tournament_id, data.name)
        if data.coach_user_id:
            self._ensure_coach(data.coach_user_id)
        return self.repos.teams.create({**data.model_dump(), "tournament_id": tournament_id})

    def update(self, team_id: UUID, data: TeamUpdate) -> Team:
        team = self.get(team_id)
        changes = data.changes()
        if "name" in changes and changes["name"].lower() != team.name.lower():
            self._ensure_unique_name(team.tournament_id, changes["name"], exclude_id=team_id)
        if changes.get("coach_user_id"):
            self._ensure_coach(changes["coach_user_id"])
        if not changes:
            return team
        return self.repos.teams.update(team_id, changes) or team

    def delete(self, team_id: UUID) -> None:
        team = self.get(team_id)
        self.repos.teams.delete(team_id)
        if team.logo_path:
            self.storage.delete(team.logo_path)

    def upload_logo(self, team_id: UUID, content: bytes, content_type: str | None, filename: str | None) -> Team:
        team = self.get(team_id)
        if content_type not in ALLOWED_LOGO_TYPES:
            raise ValidationError(f"Formato no permitido. Usa: {', '.join(ALLOWED_LOGO_TYPES)}")
        if not content:
            raise ValidationError("El archivo esta vacio")
        if len(content) > self.max_logo_bytes:
            raise ValidationError(f"El logo excede {self.max_logo_bytes // (1024 * 1024)} MB")

        extension = PurePath(filename or "").suffix.lower() or ALLOWED_LOGO_TYPES[content_type]
        # Nombre unico por subida: evita que el CDN sirva el logo anterior desde cache
        path = f"{team.tournament_id}/{team.id}/{uuid4().hex}{extension}"
        url = self.storage.upload(path, content, content_type)
        updated = self.repos.teams.update(team_id, {"logo_url": url, "logo_path": path}) or team
        if team.logo_path:
            self.storage.delete(team.logo_path)
        return updated

    def _ensure_unique_name(self, tournament_id: UUID, name: str, exclude_id: UUID | None = None) -> None:
        for other in self.repos.teams.list(filters={"tournament_id": tournament_id}):
            if other.id != exclude_id and other.name.strip().lower() == name.strip().lower():
                raise ConflictError(f"Ya existe un equipo llamado '{name}' en este torneo")

    def _ensure_coach(self, user_id: UUID) -> None:
        profile = self.repos.profiles.get(user_id)
        if profile is None:
            raise ValidationError("El usuario coach no existe")
        if profile.role != UserRole.COACH:
            raise ValidationError("El usuario asignado debe tener rol 'coach'")
