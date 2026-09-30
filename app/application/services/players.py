from uuid import UUID

from app.application.actor import Actor
from app.application.dto import PlayerCreate, PlayerUpdate
from app.application.services.teams import TeamService
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.domain.entities import Player, Team
from app.domain.repositories import Repositories


class PlayerService:
    """El admin gestiona cualquier equipo; un coach solo los equipos que tiene asignados."""

    def __init__(self, repos: Repositories, teams: TeamService) -> None:
        self.repos = repos
        self.teams = teams

    def list_by_team(self, team_id: UUID, include_inactive: bool = True) -> list[Player]:
        self.teams.get(team_id)
        filters: dict = {"team_id": team_id}
        if not include_inactive:
            filters["is_active"] = True
        return self.repos.players.list(filters=filters, order_by=["jersey_number", "full_name"])

    def list_visible(self, actor: Actor | None, team_id: UUID) -> list[Player]:
        """El publico ve solo jugadores activos; admin y coach del equipo ven tambien las bajas."""
        team = self.teams.get(team_id)
        return self.list_by_team(team_id, include_inactive=self.can_manage_team(actor, team))

    def get(self, player_id: UUID) -> Player:
        player = self.repos.players.get(player_id)
        if player is None:
            raise NotFoundError("Jugador", player_id)
        return player

    @staticmethod
    def can_manage_team(actor: Actor | None, team: Team) -> bool:
        if actor is None:
            return False
        return actor.is_admin or team.coach_user_id == actor.id

    def create(self, actor: Actor, team_id: UUID, data: PlayerCreate) -> Player:
        team = self.teams.get(team_id)
        self._ensure_can_manage(actor, team)
        if data.is_active:
            self._ensure_jersey_free(team_id, data.jersey_number)
        return self.repos.players.create({**data.model_dump(), "team_id": team_id})

    def update(self, actor: Actor, player_id: UUID, data: PlayerUpdate) -> Player:
        player = self.get(player_id)
        self._ensure_can_manage(actor, self.teams.get(player.team_id))
        changes = data.changes()
        jersey = changes.get("jersey_number", player.jersey_number)
        if changes.get("is_active", player.is_active):
            self._ensure_jersey_free(player.team_id, jersey, exclude_id=player_id)
        if not changes:
            return player
        return self.repos.players.update(player_id, changes) or player

    def delete(self, actor: Actor, player_id: UUID) -> None:
        player = self.get(player_id)
        self._ensure_can_manage(actor, self.teams.get(player.team_id))
        self.repos.players.delete(player_id)

    def _ensure_can_manage(self, actor: Actor, team: Team) -> None:
        if not self.can_manage_team(actor, team):
            raise PermissionDeniedError("Solo puedes administrar jugadores de tu propio equipo")

    def _ensure_jersey_free(self, team_id: UUID, jersey: int | None, exclude_id: UUID | None = None) -> None:
        if jersey is None:
            return
        taken = self.repos.players.list(filters={"team_id": team_id, "jersey_number": jersey, "is_active": True})
        if any(p.id != exclude_id for p in taken):
            raise ConflictError(f"El numero {jersey} ya lo usa otro jugador activo del equipo")
