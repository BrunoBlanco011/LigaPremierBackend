"""Estado de cuenta por equipo (logica pura de dominio).

Adeudo = inscripcion + multas + otros cargos - abonos (igual que la hoja del
ROL DE JUEGOS: INSCRIPCION + MULTAS - ABONOS = DEBE).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.entities import FinanceMovement, Team
from app.domain.enums import FinanceMovementType

_ZERO = Decimal("0.00")


@dataclass
class TeamBalance:
    team_id: UUID
    team_name: str
    registration_fees: Decimal = _ZERO
    fines: Decimal = _ZERO
    other_charges: Decimal = _ZERO
    payments: Decimal = _ZERO

    @property
    def total_charges(self) -> Decimal:
        return self.registration_fees + self.fines + self.other_charges

    @property
    def balance(self) -> Decimal:
        """Positivo = el equipo debe; negativo = saldo a favor."""
        return self.total_charges - self.payments


_FIELD_BY_TYPE = {
    FinanceMovementType.REGISTRATION_FEE: "registration_fees",
    FinanceMovementType.FINE: "fines",
    FinanceMovementType.OTHER_CHARGE: "other_charges",
    FinanceMovementType.PAYMENT: "payments",
}


def team_balances(teams: Iterable[Team], movements: Iterable[FinanceMovement]) -> list[TeamBalance]:
    balances = {t.id: TeamBalance(team_id=t.id, team_name=t.name) for t in teams}
    for movement in movements:
        row = balances.get(movement.team_id)
        if row is None:
            continue
        field = _FIELD_BY_TYPE[movement.type]
        setattr(row, field, getattr(row, field) + movement.amount)
    return sorted(balances.values(), key=lambda b: (-b.balance, b.team_name.lower()))
