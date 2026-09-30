"""Calculo de la tabla de posiciones (logica pura de dominio).

Reglas (basadas en el ROL DE JUEGOS de la liga):
- Solo cuentan partidos `finished` y `forfeit`. Los cancelados/pendientes no.
- JJ = juegos jugados, JG = ganados, JE = empatados, JP = perdidos.
- A favor / En contra = puntos anotados / recibidos; Diferencia = AF - EC.
- Puntos = JG*points_win + JE*points_draw + JP*points_loss + ajustes manuales.
- En un forfeit pierde `forfeit_loser_team_id` sin importar el marcador
  capturado (normalmente el admin registra algo como 21-0).
- Desempate: puntos, diferencia, puntos a favor, menos puntos en contra, nombre.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from app.domain.entities import Match, StandingAdjustment, Team, Tournament
from app.domain.enums import MatchStatus


@dataclass
class StandingRow:
    team_id: UUID
    team_name: str
    logo_url: str | None = None
    position: int = 0
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    points_for: int = 0
    points_against: int = 0
    adjustment_points: int = 0
    points: int = 0
    adjustment_reasons: list[str] = field(default_factory=list)

    @property
    def point_difference(self) -> int:
        return self.points_for - self.points_against


def winner_team_id(match: Match) -> UUID | None:
    """Ganador de un partido que cuenta para la tabla; None si es empate o no se ha jugado."""
    if not match.status.counts_for_standings:
        return None
    if match.status == MatchStatus.FORFEIT and match.forfeit_loser_team_id:
        return match.away_team_id if match.forfeit_loser_team_id == match.home_team_id else match.home_team_id
    home, away = match.home_score or 0, match.away_score or 0
    if home == away:
        return None
    return match.home_team_id if home > away else match.away_team_id


def compute_standings(
    tournament: Tournament,
    teams: Iterable[Team],
    matches: Iterable[Match],
    adjustments: Iterable[StandingAdjustment] = (),
) -> list[StandingRow]:
    rows = {t.id: StandingRow(team_id=t.id, team_name=t.name, logo_url=t.logo_url) for t in teams}

    for match in matches:
        if not match.status.counts_for_standings:
            continue
        home, away = rows.get(match.home_team_id), rows.get(match.away_team_id)
        if home is None or away is None:
            continue
        home_score, away_score = match.home_score or 0, match.away_score or 0

        home.played += 1
        away.played += 1
        home.points_for += home_score
        home.points_against += away_score
        away.points_for += away_score
        away.points_against += home_score

        winner = winner_team_id(match)
        if winner == match.home_team_id:
            home.won += 1
            away.lost += 1
        elif winner == match.away_team_id:
            away.won += 1
            home.lost += 1
        else:
            home.drawn += 1
            away.drawn += 1

    for adj in adjustments:
        row = rows.get(adj.team_id)
        if row is not None:
            row.adjustment_points += adj.points
            row.adjustment_reasons.append(adj.reason)

    for row in rows.values():
        row.points = (
            row.won * tournament.points_win
            + row.drawn * tournament.points_draw
            + row.lost * tournament.points_loss
            + row.adjustment_points
        )

    ordered = sorted(
        rows.values(),
        key=lambda r: (-r.points, -r.point_difference, -r.points_for, r.points_against, r.team_name.lower()),
    )
    for position, row in enumerate(ordered, start=1):
        row.position = position
    return ordered
