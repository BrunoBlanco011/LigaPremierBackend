from dataclasses import asdict
from typing import Literal
from uuid import UUID

from app.application.dto import PlayerStatLine
from app.application.read_models import PlayerSeasonView, PlayerStatsDetail, PlayerTotalsView
from app.application.services.matches import MatchService
from app.application.services.tournaments import TournamentService
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.entities import PlayerMatchStats
from app.domain.player_stats import aggregate_by_team, career_totals
from app.domain.repositories import Repositories

StatSortField = Literal["touchdowns", "td_passes", "interceptions", "sacks", "tackles", "games_attended"]


class StatsService:
    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.tournaments = TournamentService(repos)
        self.matches = MatchService(repos)

    # ------------------------------------------------------------ por partido
    def list_match_stats(self, match_id: UUID) -> list[PlayerMatchStats]:
        self.matches.get(match_id)
        return self.repos.player_stats.list(filters={"match_id": match_id})

    def save_match_stats(self, match_id: UUID, lines: list[PlayerStatLine]) -> list[PlayerMatchStats]:
        """Crea o reemplaza la hoja de estadisticas de los jugadores enviados."""
        match = self.matches.get(match_id)
        player_ids = [line.player_id for line in lines]
        if len(set(player_ids)) != len(player_ids):
            raise ValidationError("Hay jugadores repetidos en la captura")
        if not lines:
            return self.list_match_stats(match_id)

        # Cada jugador se registra con la inscripcion (equipo) de su club en este partido
        teams = self.repos.teams.list(in_filters={"id": [match.home_team_id, match.away_team_id]})
        team_by_club = {t.club_id: t.id for t in teams}
        players = {p.id: p for p in self.repos.players.list(in_filters={"id": player_ids})}
        invalid = [str(pid) for pid in player_ids if pid not in players or players[pid].club_id not in team_by_club]
        if invalid:
            raise ValidationError(f"Jugadores que no pertenecen a los equipos del partido: {', '.join(invalid)}")

        rows = [
            {**line.model_dump(), "match_id": match_id, "team_id": team_by_club[players[line.player_id].club_id]}
            for line in lines
        ]
        self.repos.player_stats.upsert_many(rows, on_conflict=["match_id", "player_id"])
        return self.list_match_stats(match_id)

    def delete_match_stat(self, match_id: UUID, player_id: UUID) -> None:
        existing = self.repos.player_stats.list(filters={"match_id": match_id, "player_id": player_id})
        if not existing:
            raise NotFoundError("Estadistica del jugador en el partido")
        self.repos.player_stats.delete(existing[0].id)

    # ------------------------------------------------------------ acumulados
    def tournament_totals(
        self,
        tournament_id: UUID,
        team_id: UUID | None = None,
        sort_by: StatSortField = "touchdowns",
        limit: int | None = None,
    ) -> list[PlayerTotalsView]:
        self.tournaments.get(tournament_id)
        teams = self.repos.teams.list(filters={"tournament_id": tournament_id})
        if team_id:
            teams = [t for t in teams if t.id == team_id]
            if not teams:
                raise ValidationError("El equipo no pertenece al torneo")
        if not teams:
            return []

        stats = self.repos.player_stats.list(in_filters={"team_id": [t.id for t in teams]})
        player_ids = {s.player_id for s in stats}
        roster = self.repos.players.list(in_filters={"club_id": [t.club_id for t in teams]})
        # Incluye a quien jugo con el equipo aunque despues haya cambiado de club
        missing = player_ids - {p.id for p in roster}
        players = roster + (self.repos.players.list(in_filters={"id": list(missing)}) if missing else [])

        totals = aggregate_by_team(players, teams, stats)
        totals.sort(key=lambda t: (-getattr(t, sort_by), t.full_name))
        views = [PlayerTotalsView(**asdict(t)) for t in totals]
        return views[:limit] if limit else views

    def player_detail(self, player_id: UUID) -> PlayerStatsDetail:
        """Carrera del jugador: total general, desglose por torneo y partido por partido."""
        player = self.repos.players.get(player_id)
        if player is None:
            raise NotFoundError("Jugador", player_id)
        club = self.repos.clubs.get(player.club_id)
        stats = self.repos.player_stats.list(filters={"player_id": player_id})

        teams = self.repos.teams.list(in_filters={"id": list({s.team_id for s in stats})}) if stats else []
        tournaments = (
            {t.id: t for t in self.repos.tournaments.list(in_filters={"id": [t.tournament_id for t in teams]})}
            if teams else {}
        )
        team_tournament = {t.id: t.tournament_id for t in teams}
        by_team = [row for row in aggregate_by_team([player], teams, stats) if row.team_id in team_tournament]
        seasons = [
            PlayerSeasonView(
                tournament_id=team_tournament[row.team_id],
                tournament_name=tournaments[team_tournament[row.team_id]].name,
                totals=PlayerTotalsView(**asdict(row)),
            )
            for row in by_team
            if team_tournament[row.team_id] in tournaments
        ]
        career = career_totals(player, club.name if club else "", stats)
        return PlayerStatsDetail(totals=PlayerTotalsView(**asdict(career)), by_tournament=seasons, matches=stats)
