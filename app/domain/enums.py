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
