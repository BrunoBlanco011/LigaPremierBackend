"""Objetos de entrada de los casos de uso (validados con Pydantic).

Los *Update* son parciales: solo se aplican los campos enviados. `changes()`
descarta los `null` en campos que no pueden quedar vacios en la base.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.enums import FinanceMovementType, MatchStatus, TournamentStatus, UserRole

ShortText = Annotated[str, Field(min_length=1, max_length=120)]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    NON_NULLABLE: ClassVar[frozenset[str]] = frozenset()

    def changes(self) -> dict[str, Any]:
        data = self.model_dump(exclude_unset=True)
        return {k: v for k, v in data.items() if not (v is None and k in self.NON_NULLABLE)}


# ---------------------------------------------------------------- Torneos
class TournamentCreate(Command):
    name: ShortText
    season: str | None = Field(default=None, max_length=60)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    status: TournamentStatus = TournamentStatus.DRAFT
    points_win: int = Field(default=2, ge=0, le=10)
    points_loss: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def _check_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date no puede ser anterior a start_date")
        return self


class TournamentUpdate(Command):
    NON_NULLABLE = frozenset({"name", "status", "points_win", "points_loss"})

    name: str | None = Field(default=None, min_length=1, max_length=120)
    season: str | None = Field(default=None, max_length=60)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    status: TournamentStatus | None = None
    points_win: int | None = Field(default=None, ge=0, le=10)
    points_loss: int | None = Field(default=None, ge=0, le=10)


# ---------------------------------------------------------------- Equipos
class TeamCreate(Command):
    name: ShortText
    coach_name: str | None = Field(default=None, max_length=120)
    coach_user_id: UUID | None = None


class TeamUpdate(Command):
    NON_NULLABLE = frozenset({"name"})

    name: str | None = Field(default=None, min_length=1, max_length=120)
    coach_name: str | None = Field(default=None, max_length=120)
    coach_user_id: UUID | None = None


# ---------------------------------------------------------------- Jugadores
class PlayerCreate(Command):
    full_name: ShortText
    jersey_number: int | None = Field(default=None, ge=0, le=999)
    is_active: bool = True


class PlayerUpdate(Command):
    NON_NULLABLE = frozenset({"full_name", "is_active"})

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    jersey_number: int | None = Field(default=None, ge=0, le=999)
    is_active: bool | None = None


# ---------------------------------------------------------------- Jornadas
class RoundCreate(Command):
    number: int = Field(ge=1, le=999)
    name: str | None = Field(default=None, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    bye_team_id: UUID | None = None


class RoundUpdate(Command):
    NON_NULLABLE = frozenset({"number"})

    number: int | None = Field(default=None, ge=1, le=999)
    name: str | None = Field(default=None, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    bye_team_id: UUID | None = None


# ---------------------------------------------------------------- Partidos
class MatchCreate(Command):
    round_id: UUID | None = None
    home_team_id: UUID
    away_team_id: UUID
    scheduled_at: datetime | None = None
    venue: str | None = Field(default=None, max_length=120)
    status: MatchStatus = MatchStatus.SCHEDULED
    home_score: int | None = Field(default=None, ge=0, le=999)
    away_score: int | None = Field(default=None, ge=0, le=999)
    forfeit_loser_team_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class MatchUpdate(Command):
    NON_NULLABLE = frozenset({"home_team_id", "away_team_id", "status"})

    round_id: UUID | None = None
    home_team_id: UUID | None = None
    away_team_id: UUID | None = None
    scheduled_at: datetime | None = None
    venue: str | None = Field(default=None, max_length=120)
    status: MatchStatus | None = None
    home_score: int | None = Field(default=None, ge=0, le=999)
    away_score: int | None = Field(default=None, ge=0, le=999)
    forfeit_loser_team_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class MatchResult(Command):
    """Captura/correccion rapida del resultado de un partido.

    Marcador final incluyendo tiempo extra (no hay empates). En un forfeit
    basta con `forfeit_loser_team_id`: el marcador se fija en 21-0.
    """

    home_score: int | None = Field(default=None, ge=0, le=999)
    away_score: int | None = Field(default=None, ge=0, le=999)
    status: MatchStatus = MatchStatus.FINISHED
    forfeit_loser_team_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------- Tabla
class AdjustmentCreate(Command):
    team_id: UUID
    points: int = Field(ge=-100, le=100)
    reason: str = Field(min_length=1, max_length=300)


class AdjustmentUpdate(Command):
    NON_NULLABLE = frozenset({"points", "reason"})

    points: int | None = Field(default=None, ge=-100, le=100)
    reason: str | None = Field(default=None, min_length=1, max_length=300)


# ---------------------------------------------------------------- Estadisticas
class PlayerStatLine(Command):
    player_id: UUID
    attended: bool = True
    touchdowns: int = Field(default=0, ge=0, le=99)
    td_passes: int = Field(default=0, ge=0, le=99)
    interceptions: int = Field(default=0, ge=0, le=99)
    sacks: int = Field(default=0, ge=0, le=99)
    tackles: int = Field(default=0, ge=0, le=99)


# ---------------------------------------------------------------- Rol de juegos
class ScheduleGenerate(Command):
    """Genera jornadas y partidos todos contra todos con los equipos del torneo."""

    start_date: date | None = Field(default=None, description="Fecha de la jornada 1")
    days_between_rounds: int = Field(default=7, ge=1, le=60)
    double_round: bool = Field(default=False, description="Ida y vuelta")
    replace_existing: bool = Field(
        default=False,
        description="Borra jornadas y partidos existentes (solo si ningun partido se ha jugado)",
    )


# ---------------------------------------------------------------- Finanzas
Money = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]


class FinanceMovementCreate(Command):
    team_id: UUID
    type: FinanceMovementType
    amount: Money
    description: str | None = Field(default=None, max_length=300)
    occurred_on: date | None = None
    match_id: UUID | None = None


class FinanceMovementUpdate(Command):
    NON_NULLABLE = frozenset({"type", "amount", "occurred_on"})

    type: FinanceMovementType | None = None
    amount: Money | None = None
    description: str | None = Field(default=None, max_length=300)
    occurred_on: date | None = None
    match_id: UUID | None = None


class RegistrationFeeCreate(Command):
    """Carga la inscripcion a todos los equipos del torneo que aun no la tengan."""

    amount: Money
    description: str | None = Field(default="Inscripcion", max_length=300)
    occurred_on: date | None = None


# ---------------------------------------------------------------- Usuarios
class UserCreate(Command):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=120)
    role: UserRole = UserRole.COACH


class UserUpdate(Command):
    NON_NULLABLE = frozenset({"role"})

    full_name: str | None = Field(default=None, max_length=120)
    role: UserRole | None = None


class LoginRequest(Command):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)
