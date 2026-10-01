"""Entidades del dominio. No dependen de FastAPI ni de Supabase."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import FinanceMovementType, MatchStatus, TournamentStatus, UserRole


class Entity(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Profile(Entity):
    email: str | None = None
    full_name: str | None = None
    role: UserRole = UserRole.COACH


class Tournament(Entity):
    name: str
    season: str | None = None
    category: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: TournamentStatus = TournamentStatus.DRAFT
    points_win: int = 2
    points_loss: int = 0


class Club(Entity):
    """Equipo permanente de la liga: se inscribe a uno o varios torneos."""

    name: str
    coach_name: str | None = None
    coach_user_id: UUID | None = None
    logo_url: str | None = None
    logo_path: str | None = None


class Team(Entity):
    """Inscripcion de un club a un torneo.

    `name`, `logo_url`, `coach_name` y `coach_user_id` son de solo lectura:
    vienen del club (vista `team_details`).
    """

    tournament_id: UUID
    club_id: UUID
    name: str = ""
    logo_url: str | None = None
    coach_name: str | None = None
    coach_user_id: UUID | None = None


class Player(Entity):
    club_id: UUID
    full_name: str
    jersey_number: int | None = None
    is_active: bool = True


class Round(Entity):
    tournament_id: UUID
    number: int
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    bye_team_id: UUID | None = None


class Match(Entity):
    tournament_id: UUID
    round_id: UUID | None = None
    home_team_id: UUID
    away_team_id: UUID
    scheduled_at: datetime | None = None
    venue: str | None = None
    status: MatchStatus = MatchStatus.SCHEDULED
    home_score: int | None = None
    away_score: int | None = None
    forfeit_loser_team_id: UUID | None = None
    notes: str | None = None


class StandingAdjustment(Entity):
    tournament_id: UUID
    team_id: UUID
    points: int
    reason: str


class PlayerMatchStats(Entity):
    match_id: UUID
    player_id: UUID
    team_id: UUID
    attended: bool = True
    touchdowns: int = 0
    td_passes: int = 0
    interceptions: int = 0
    sacks: int = 0
    tackles: int = 0


class FinanceMovement(Entity):
    tournament_id: UUID
    team_id: UUID
    type: FinanceMovementType
    amount: Decimal
    description: str | None = None
    occurred_on: date | None = None
    match_id: UUID | None = None


class ClubInvite(Entity):
    """Link temporal para que los jugadores se den de alta en un club."""

    club_id: UUID
    token: str
    expires_at: datetime
    created_by: UUID | None = None
