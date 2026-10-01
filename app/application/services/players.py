from uuid import UUID

from app.application.actor import Actor
from app.application.dto import PlayerCreate, PlayerUpdate
from app.application.services.clubs import ClubService
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.domain.entities import Club, Player
from app.domain.repositories import Repositories


class PlayerService:
    """Los jugadores pertenecen al club y se conservan entre torneos.

    El admin gestiona cualquier club; un coach solo los clubes que tiene asignados.
    """

    def __init__(self, repos: Repositories, clubs: ClubService) -> None:
        self.repos = repos
        self.clubs = clubs

    def list_by_club(self, club_id: UUID, include_inactive: bool = True) -> list[Player]:
        self.clubs.get(club_id)
        filters: dict = {"club_id": club_id}
        if not include_inactive:
            filters["is_active"] = True
        return self.repos.players.list(filters=filters, order_by=["jersey_number", "full_name"])

    def list_visible(self, actor: Actor | None, club_id: UUID) -> list[Player]:
        """El publico ve solo jugadores activos; admin y coach del club ven tambien las bajas."""
        club = self.clubs.get(club_id)
        return self.list_by_club(club_id, include_inactive=self.can_manage_club(actor, club))

    def get(self, player_id: UUID) -> Player:
        player = self.repos.players.get(player_id)
        if player is None:
            raise NotFoundError("Jugador", player_id)
        return player

    @staticmethod
    def can_manage_club(actor: Actor | None, club: Club) -> bool:
        if actor is None:
            return False
        return actor.is_admin or club.coach_user_id == actor.id

    def create(self, actor: Actor, club_id: UUID, data: PlayerCreate) -> Player:
        club = self.clubs.get(club_id)
        self._ensure_can_manage(actor, club)
        if data.is_active:
            self._ensure_jersey_free(club_id, data.jersey_number)
        return self.repos.players.create({**data.model_dump(), "club_id": club_id})

    def update(self, actor: Actor, player_id: UUID, data: PlayerUpdate) -> Player:
        player = self.get(player_id)
        self._ensure_can_manage(actor, self.clubs.get(player.club_id))
        changes = data.changes()

        target_club = changes.get("club_id", player.club_id)
        if target_club != player.club_id:
            if not actor.is_admin:
                raise PermissionDeniedError("Solo el administrador puede transferir jugadores entre clubes")
            self.clubs.get(target_club)

        if changes.get("is_active", player.is_active):
            jersey = changes.get("jersey_number", player.jersey_number)
            self._ensure_jersey_free(target_club, jersey, exclude_id=player_id)
        if not changes:
            return player
        return self.repos.players.update(player_id, changes) or player

    def delete(self, actor: Actor, player_id: UUID) -> None:
        player = self.get(player_id)
        self._ensure_can_manage(actor, self.clubs.get(player.club_id))
        self.repos.players.delete(player_id)

    def register_via_invite(self, club_id: UUID, data: PlayerCreate) -> Player:
        """Alta publica desde un link de invitacion (el token ya fue validado)."""
        self.clubs.get(club_id)
        if data.is_active:
            self._ensure_jersey_free(club_id, data.jersey_number)
        return self.repos.players.create({**data.model_dump(), "club_id": club_id})

    def _ensure_can_manage(self, actor: Actor, club: Club) -> None:
        if not self.can_manage_club(actor, club):
            raise PermissionDeniedError("Solo puedes administrar jugadores de tu propio club")

    def _ensure_jersey_free(self, club_id: UUID, jersey: int | None, exclude_id: UUID | None = None) -> None:
        if jersey is None:
            return
        taken = self.repos.players.list(filters={"club_id": club_id, "jersey_number": jersey, "is_active": True})
        if any(p.id != exclude_id for p in taken):
            raise ConflictError(f"El numero {jersey} ya lo usa otro jugador activo del club")
