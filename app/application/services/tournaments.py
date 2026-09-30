from __future__ import annotations

from uuid import UUID

from app.application.dto import TournamentCreate, TournamentUpdate
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.entities import Tournament
from app.domain.enums import TournamentStatus
from app.domain.repositories import Repositories


class TournamentService:
    def __init__(self, repos: Repositories) -> None:
        self.repos = repos

    def list(self, status: TournamentStatus | None = None) -> list[Tournament]:
        filters = {"status": status} if status else None
        return self.repos.tournaments.list(filters=filters, order_by=["-start_date", "name"])

    def get(self, tournament_id: UUID) -> Tournament:
        tournament = self.repos.tournaments.get(tournament_id)
        if tournament is None:
            raise NotFoundError("Torneo", tournament_id)
        return tournament

    def create(self, data: TournamentCreate) -> Tournament:
        return self.repos.tournaments.create(data.model_dump())

    def update(self, tournament_id: UUID, data: TournamentUpdate) -> Tournament:
        current = self.get(tournament_id)
        changes = data.changes()
        start = changes.get("start_date", current.start_date)
        end = changes.get("end_date", current.end_date)
        if start and end and end < start:
            raise ValidationError("end_date no puede ser anterior a start_date")
        if not changes:
            return current
        updated = self.repos.tournaments.update(tournament_id, changes)
        if updated is None:
            raise NotFoundError("Torneo", tournament_id)
        return updated

    def delete(self, tournament_id: UUID) -> None:
        if not self.repos.tournaments.delete(tournament_id):
            raise NotFoundError("Torneo", tournament_id)
