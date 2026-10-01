"""Modelos de lectura: vistas enriquecidas pensadas para el frontend."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.domain.entities import Match, PlayerMatchStats, Tournament


class TeamSummary(BaseModel):
    id: UUID
    name: str
    logo_url: str | None = None


class RoundSummary(BaseModel):
    id: UUID
    number: int
    name: str | None = None


class MatchView(Match):
    home_team: TeamSummary | None = None
    away_team: TeamSummary | None = None
    round: RoundSummary | None = None
    winner_team_id: UUID | None = None


class StandingView(BaseModel):
    position: int
    team: TeamSummary
    played: int
    won: int
    lost: int
    points_for: int
    points_against: int
    point_difference: int
    adjustment_points: int
    adjustment_reasons: list[str]
    points: int


class PlayerTotalsView(BaseModel):
    player_id: UUID
    full_name: str
    jersey_number: int | None
    team_id: UUID | None = None
    team_name: str
    games_attended: int
    touchdowns: int
    td_passes: int
    interceptions: int
    sacks: int
    tackles: int


class PlayerSeasonView(BaseModel):
    tournament_id: UUID
    tournament_name: str
    totals: PlayerTotalsView


class PlayerStatsDetail(BaseModel):
    totals: PlayerTotalsView
    """Acumulado de toda la carrera (team_id nulo, team_name = club actual)."""
    by_tournament: list[PlayerSeasonView]
    matches: list[PlayerMatchStats]


class ClubSeason(BaseModel):
    """Participacion de un club en un torneo."""

    tournament: Tournament
    team_id: UUID
    standing: StandingView | None
    teams_count: int


class ScheduleResult(BaseModel):
    rounds_created: int
    matches_created: int


class TeamBalanceView(BaseModel):
    team: TeamSummary
    registration_fees: Decimal
    fines: Decimal
    other_charges: Decimal
    total_charges: Decimal
    payments: Decimal
    balance: Decimal


class FinanceSummary(BaseModel):
    teams: list[TeamBalanceView]
    total_charges: Decimal
    total_payments: Decimal
    total_balance: Decimal


class ClubInviteInfo(BaseModel):
    """Datos publicos de una invitacion valida (para la pagina de auto-registro)."""

    club: TeamSummary
    expires_at: datetime
