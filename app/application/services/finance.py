from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.dto import FinanceMovementCreate, FinanceMovementUpdate, RegistrationFeeCreate
from app.application.read_models import FinanceSummary, TeamBalanceView, TeamSummary
from app.application.services.tournaments import TournamentService
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.entities import FinanceMovement
from app.domain.enums import FinanceMovementType
from app.domain.finance import team_balances
from app.domain.repositories import Repositories


class FinanceService:
    """Estado de cuenta de los equipos: inscripciones, multas, otros cargos y abonos. Solo admin."""

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.tournaments = TournamentService(repos)

    def summary(self, tournament_id: UUID) -> FinanceSummary:
        self.tournaments.get(tournament_id)
        teams = self.repos.teams.list(filters={"tournament_id": tournament_id})
        movements = self.repos.finance.list(filters={"tournament_id": tournament_id})
        logos = {t.id: t.logo_url for t in teams}
        balances = team_balances(teams, movements)
        return FinanceSummary(
            teams=[
                TeamBalanceView(
                    team=TeamSummary(id=b.team_id, name=b.team_name, logo_url=logos.get(b.team_id)),
                    registration_fees=b.registration_fees,
                    fines=b.fines,
                    other_charges=b.other_charges,
                    total_charges=b.total_charges,
                    payments=b.payments,
                    balance=b.balance,
                )
                for b in balances
            ],
            total_charges=sum((b.total_charges for b in balances), Decimal("0.00")),
            total_payments=sum((b.payments for b in balances), Decimal("0.00")),
            total_balance=sum((b.balance for b in balances), Decimal("0.00")),
        )

    def list_movements(
        self,
        tournament_id: UUID,
        team_id: UUID | None = None,
        movement_type: FinanceMovementType | None = None,
    ) -> list[FinanceMovement]:
        self.tournaments.get(tournament_id)
        filters: dict[str, Any] = {"tournament_id": tournament_id}
        if team_id:
            filters["team_id"] = team_id
        if movement_type:
            filters["type"] = movement_type
        return self.repos.finance.list(filters=filters, order_by=["-occurred_on", "-created_at"])

    def create(self, tournament_id: UUID, data: FinanceMovementCreate) -> FinanceMovement:
        self.tournaments.get(tournament_id)
        self._ensure_team(tournament_id, data.team_id)
        self._ensure_match(tournament_id, data.match_id)
        payload = data.model_dump(exclude_none=True)
        return self.repos.finance.create({**payload, "tournament_id": tournament_id})

    def update(self, movement_id: UUID, data: FinanceMovementUpdate) -> FinanceMovement:
        movement = self._get(movement_id)
        changes = data.changes()
        if changes.get("match_id"):
            self._ensure_match(movement.tournament_id, changes["match_id"])
        if not changes:
            return movement
        return self.repos.finance.update(movement_id, changes) or movement

    def delete(self, movement_id: UUID) -> None:
        if not self.repos.finance.delete(movement_id):
            raise NotFoundError("Movimiento", movement_id)

    def charge_registration_fees(self, tournament_id: UUID, data: RegistrationFeeCreate) -> list[FinanceMovement]:
        """Carga la inscripcion a cada equipo del torneo que todavia no la tenga."""
        self.tournaments.get(tournament_id)
        teams = self.repos.teams.list(filters={"tournament_id": tournament_id})
        charged = {
            m.team_id
            for m in self.repos.finance.list(
                filters={"tournament_id": tournament_id, "type": FinanceMovementType.REGISTRATION_FEE}
            )
        }
        extra = {"occurred_on": data.occurred_on} if data.occurred_on else {}
        return self.repos.finance.create_many([
            {
                "tournament_id": tournament_id,
                "team_id": team.id,
                "type": FinanceMovementType.REGISTRATION_FEE,
                "amount": data.amount,
                "description": data.description,
                **extra,
            }
            for team in teams
            if team.id not in charged
        ])

    def _get(self, movement_id: UUID) -> FinanceMovement:
        movement = self.repos.finance.get(movement_id)
        if movement is None:
            raise NotFoundError("Movimiento", movement_id)
        return movement

    def _ensure_team(self, tournament_id: UUID, team_id: UUID) -> None:
        team = self.repos.teams.get(team_id)
        if team is None or team.tournament_id != tournament_id:
            raise ValidationError("El equipo no pertenece al torneo")

    def _ensure_match(self, tournament_id: UUID, match_id: UUID | None) -> None:
        if match_id is None:
            return
        match = self.repos.matches.get(match_id)
        if match is None or match.tournament_id != tournament_id:
            raise ValidationError("El partido no pertenece al torneo")
