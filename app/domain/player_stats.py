"""Acumulado de estadisticas por jugador (logica pura de dominio)."""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from app.domain.entities import Player, PlayerMatchStats, Team

STAT_FIELDS = ("touchdowns", "td_passes", "interceptions", "sacks", "tackles")


@dataclass
class PlayerTotals:
    player_id: UUID
    full_name: str
    jersey_number: int | None
    team_id: UUID
    team_name: str
    games_attended: int = 0
    touchdowns: int = 0
    td_passes: int = 0
    interceptions: int = 0
    sacks: int = 0
    tackles: int = 0


def aggregate_player_stats(
    players: Iterable[Player],
    teams: Iterable[Team],
    stats: Iterable[PlayerMatchStats],
) -> list[PlayerTotals]:
    team_names = {t.id: t.name for t in teams}
    totals = {
        p.id: PlayerTotals(
            player_id=p.id,
            full_name=p.full_name,
            jersey_number=p.jersey_number,
            team_id=p.team_id,
            team_name=team_names.get(p.team_id, ""),
        )
        for p in players
    }
    for line in stats:
        row = totals.get(line.player_id)
        if row is None:
            continue
        if line.attended:
            row.games_attended += 1
        for stat in STAT_FIELDS:
            setattr(row, stat, getattr(row, stat) + getattr(line, stat))
    return list(totals.values())
