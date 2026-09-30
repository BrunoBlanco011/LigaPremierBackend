from datetime import date
from uuid import UUID

from app.application.dto import RoundCreate, RoundUpdate
from app.application.services.tournaments import TournamentService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.entities import Round
from app.domain.repositories import Repositories


class RoundService:
    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.tournaments = TournamentService(repos)

    def list_by_tournament(self, tournament_id: UUID) -> list[Round]:
        self.tournaments.get(tournament_id)
        return self.repos.rounds.list(filters={"tournament_id": tournament_id}, order_by=["number"])

    def get(self, round_id: UUID) -> Round:
        round_ = self.repos.rounds.get(round_id)
        if round_ is None:
            raise NotFoundError("Jornada", round_id)
        return round_

    def create(self, tournament_id: UUID, data: RoundCreate) -> Round:
        self.tournaments.get(tournament_id)
        self._validate_dates(data.start_date, data.end_date)
        self._ensure_number_free(tournament_id, data.number)
        payload = data.model_dump()
        payload["name"] = payload["name"] or f"Jornada {data.number}"
        return self.repos.rounds.create({**payload, "tournament_id": tournament_id})

    def update(self, round_id: UUID, data: RoundUpdate) -> Round:
        round_ = self.get(round_id)
        changes = data.changes()
        self._validate_dates(changes.get("start_date", round_.start_date), changes.get("end_date", round_.end_date))
        if "number" in changes and changes["number"] != round_.number:
            self._ensure_number_free(round_.tournament_id, changes["number"])
        if not changes:
            return round_
        return self.repos.rounds.update(round_id, changes) or round_

    def delete(self, round_id: UUID) -> None:
        """Los partidos de la jornada se conservan (quedan sin jornada asignada)."""
        if not self.repos.rounds.delete(round_id):
            raise NotFoundError("Jornada", round_id)

    def _ensure_number_free(self, tournament_id: UUID, number: int) -> None:
        if self.repos.rounds.list(filters={"tournament_id": tournament_id, "number": number}):
            raise ConflictError(f"Ya existe la jornada {number} en este torneo")

    @staticmethod
    def _validate_dates(start: date | None, end: date | None) -> None:
        if start and end and end < start:
            raise ValidationError("end_date no puede ser anterior a start_date")
