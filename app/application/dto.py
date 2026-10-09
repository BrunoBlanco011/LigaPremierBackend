"""Objetos de entrada de los casos de uso (validados con Pydantic).

Los *Update* son parciales: solo se aplican los campos enviados. `changes()`
descarta los `null` en campos que no pueden quedar vacios en la base.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal
from typing import Annotated, Any, ClassVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator

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
    """La fecha de fin y la temporada no se capturan: el fin lo marca el rol de juegos
    (depende de cuantos equipos se inscriban) y los puntos son fijos (2 por victoria, 0 por derrota)."""

    name: ShortText
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    status: TournamentStatus = TournamentStatus.DRAFT


class TournamentUpdate(Command):
    NON_NULLABLE = frozenset({"name", "status"})

    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    status: TournamentStatus | None = None


# ---------------------------------------------------------------- Clubes
class ClubCreate(Command):
    name: ShortText
    coach_name: str | None = Field(default=None, max_length=120)
    coach_user_id: UUID | None = None


class ClubUpdate(Command):
    NON_NULLABLE = frozenset({"name"})

    name: str | None = Field(default=None, min_length=1, max_length=120)
    coach_name: str | None = Field(default=None, max_length=120)
    coach_user_id: UUID | None = None


# ---------------------------------------------------------------- Inscripciones
class TeamRegister(Command):
    """Inscribe uno o varios clubes a un torneo."""

    club_ids: list[UUID] = Field(min_length=1, max_length=100)


# ---------------------------------------------------------------- Jugadores
def _check_birth_date(value: date | None) -> date | None:
    if value is not None and not date(1900, 1, 1) <= value <= date.today():
        raise ValueError("La fecha de nacimiento no puede ser futura ni anterior a 1900")
    return value


BirthDate = Annotated[date | None, AfterValidator(_check_birth_date)]


class PlayerCreate(Command):
    full_name: ShortText
    jersey_number: int | None = Field(default=None, ge=0, le=999)
    birth_date: BirthDate = None
    is_active: bool = True


class PlayerUpdate(Command):
    NON_NULLABLE = frozenset({"full_name", "is_active", "club_id"})

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    jersey_number: int | None = Field(default=None, ge=0, le=999)
    birth_date: BirthDate = None
    is_active: bool | None = None
    club_id: UUID | None = Field(default=None, description="Transferir a otro club (solo admin)")


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

    start_date: date | None = Field(
        default=None, description="A partir de esta fecha se programan las jornadas (sin fecha: jornadas sin fecha)"
    )
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(
        default_factory=list,
        description="Dias de juego, 0=lunes ... 6=domingo. Vacio: el dia de la semana de start_date",
    )
    start_time: time | None = Field(default=None, description="Hora del primer partido de cada jornada")
    match_duration_minutes: int = Field(
        default=60, ge=10, le=300, description="Los partidos de un mismo dia se juegan uno tras otro"
    )
    max_matches_per_day: int | None = Field(
        default=None, ge=1, le=50,
        description="Si la jornada tiene mas partidos, sigue en el siguiente dia de juego. Vacio: sin limite",
    )
    venue: str | None = Field(default=None, max_length=120, description="Sede de todos los partidos generados")
    timezone: str = Field(default="America/Mexico_City", description="Zona horaria de start_time")
    double_round: bool = Field(default=False, description="Ida y vuelta")
    replace_existing: bool = Field(
        default=False,
        description="Borra jornadas y partidos existentes (solo si ningun partido se ha jugado)",
    )

    @model_validator(mode="after")
    def _check_schedule(self):
        if (self.weekdays or self.start_time) and not self.start_date:
            raise ValueError("Indica la fecha a partir de la cual se programan las jornadas")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Zona horaria desconocida: {self.timezone}") from None
        return self


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
    password: str = Field(min_length=8, max_length=72, description="Minimo 8 caracteres, con letras y numeros")
    full_name: str | None = Field(default=None, max_length=120)
    role: UserRole = UserRole.COACH

    @model_validator(mode="after")
    def _check_password(self):
        password = self.password
        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            raise ValueError("La contrasena debe tener letras y numeros")
        if self.email.split("@")[0].lower() in password.lower():
            raise ValueError("La contrasena no debe contener el correo")
        if len(password.encode("utf-8")) > 72:
            raise ValueError("La contrasena es demasiado larga")
        return self


class UserUpdate(Command):
    NON_NULLABLE = frozenset({"role"})

    full_name: str | None = Field(default=None, max_length=120)
    role: UserRole | None = None


class LoginRequest(Command):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)
