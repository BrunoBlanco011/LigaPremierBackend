from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    COACH = "coach"


class TournamentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    FORFEIT = "forfeit"

    @property
    def counts_for_standings(self) -> bool:
        return self in (MatchStatus.FINISHED, MatchStatus.FORFEIT)


class FinanceMovementType(StrEnum):
    REGISTRATION_FEE = "registration_fee"
    FINE = "fine"
    OTHER_CHARGE = "other_charge"
    PAYMENT = "payment"

    @property
    def is_charge(self) -> bool:
        return self != FinanceMovementType.PAYMENT
