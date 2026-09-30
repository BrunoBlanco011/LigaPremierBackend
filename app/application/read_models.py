"""Modelos de lectura: vistas enriquecidas pensadas para el frontend."""

from uuid import UUID

from pydantic import BaseModel

from app.domain.entities import Match, PlayerMatchStats


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
    drawn: int
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
    team_id: UUID
    team_name: str
    games_attended: int
    touchdowns: int
    td_passes: int
    interceptions: int
    sacks: int
    tackles: int


class PlayerStatsDetail(BaseModel):
    totals: PlayerTotalsView
    matches: list[PlayerMatchStats]
