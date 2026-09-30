"""Acumulado de estadisticas por jugador (logica pura de dominio).

Cada linea de estadistica guarda la inscripcion (`team_id`) con la que se
jugo el partido, asi el acumulado por torneo respeta el equipo de ese torneo
aunque el jugador cambie de club despues.
"""

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
    team_id: UUID | None
    team_name: str
    games_attended: int = 0
    touchdowns: int = 0
    td_passes: int = 0
    interceptions: int = 0
    sacks: int = 0
    tackles: int = 0

    def add(self, line: PlayerMatchStats) -> None:
        if line.attended:
            self.games_attended += 1
        for stat in STAT_FIELDS:
            setattr(self, stat, getattr(self, stat) + getattr(line, stat))


def aggregate_by_team(
    players: Iterable[Player],
    teams: Iterable[Team],
    stats: Iterable[PlayerMatchStats],
) -> list[PlayerTotals]:
    """Un renglon por (jugador, inscripcion).

    Se incluyen en cero los jugadores activos de los clubes inscritos, para que
    aparezcan aunque aun no tengan estadisticas.
    """
    players_by_id = {p.id: p for p in players}
    teams_by_id = {t.id: t for t in teams}
    totals: dict[tuple[UUID, UUID], PlayerTotals] = {}

    def row(player: Player, team: Team) -> PlayerTotals:
        key = (player.id, team.id)
        if key not in totals:
            totals[key] = PlayerTotals(player.id, player.full_name, player.jersey_number, team.id, team.name)
        return totals[key]

    for team in teams_by_id.values():
        for player in players_by_id.values():
            if player.is_active and player.club_id == team.club_id:
                row(player, team)

    for line in stats:
        player, team = players_by_id.get(line.player_id), teams_by_id.get(line.team_id)
        if player is not None and team is not None:
            row(player, team).add(line)
    return list(totals.values())


def career_totals(player: Player, club_name: str, stats: Iterable[PlayerMatchStats]) -> PlayerTotals:
    """Acumulado de toda la carrera del jugador en la liga."""
    totals = PlayerTotals(player.id, player.full_name, player.jersey_number, None, club_name)
    for line in stats:
        totals.add(line)
    return totals
