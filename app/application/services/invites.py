from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.actor import Actor
from app.application.dto import PlayerCreate
from app.application.read_models import ClubInviteInfo, TeamSummary
from app.application.services.clubs import ClubService
from app.application.services.players import PlayerService
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.domain.entities import Club, ClubInvite, Player
from app.domain.repositories import Repositories

DEFAULT_TTL_HOURS = 24
MAX_TTL_HOURS = 168  # 7 dias


class InviteService:
    """Links temporales para que los jugadores se den de alta en su club."""

    def __init__(self, repos: Repositories, clubs: ClubService, players: PlayerService) -> None:
        self.repos = repos
        self.clubs = clubs
        self.players = players

    def create(self, actor: Actor, club_id: UUID, ttl_hours: int = DEFAULT_TTL_HOURS) -> ClubInvite:
        club = self.clubs.get(club_id)
        if not ClubService.can_manage(actor, club):
            raise PermissionDeniedError("Solo el coach del club o un admin puede generar invitaciones")
        ttl = max(1, min(ttl_hours, MAX_TTL_HOURS))
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)
        return self.repos.club_invites.create(
            {
                "club_id": club_id,
                "token": secrets.token_urlsafe(24),
                "expires_at": expires_at,
                "created_by": actor.id,
            }
        )

    def info(self, token: str) -> ClubInviteInfo:
        invite, club = self._resolve(token)
        return ClubInviteInfo(
            club=TeamSummary(id=club.id, name=club.name, logo_url=club.logo_url),
            expires_at=invite.expires_at,
        )

    def redeem(self, token: str, data: PlayerCreate) -> Player:
        _, club = self._resolve(token)
        return self.players.register_via_invite(club.id, data)

    def _resolve(self, token: str) -> tuple[ClubInvite, Club]:
        found = self.repos.club_invites.list(filters={"token": token})
        if not found:
            raise NotFoundError("Invitacion", token)
        invite = found[0]
        if invite.expires_at < datetime.now(timezone.utc):
            raise ValidationError("El link de invitacion expiro. Pide uno nuevo al coach.")
        return invite, self.clubs.get(invite.club_id)
