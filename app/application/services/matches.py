from __future__ import annotations

from typing import Any
from uuid import UUID

from app.application.dto import MatchCreate, MatchResult, MatchUpdate
from app.application.read_models import (
    MatchView,
    RefereeSheet,
    RefereeSheetPlayer,
    RefereeSheetTeam,
    RoundSummary,
    TeamSummary,
)
from app.application.services.tournaments import TournamentService
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.entities import Match
from app.domain.enums import MatchStatus
from app.domain.repositories import Repositories
from app.domain.rules import forfeit_scores
from app.domain.standings import winner_team_id


class MatchService:
    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.tournaments = TournamentService(repos)

    # ------------------------------------------------------------ lectura
    def list(
        self,
        tournament_id: UUID,
        round_id: UUID | None = None,
        team_id: UUID | None = None,
        status: MatchStatus | None = None,
    ) -> list[MatchView]:
        self.tournaments.get(tournament_id)
        filters: dict[str, Any] = {"tournament_id": tournament_id}
        if round_id:
            filters["round_id"] = round_id
        if status:
            filters["status"] = status
        matches = self.repos.matches.list(filters=filters, order_by=["scheduled_at"])
        if team_id:
            matches = [m for m in matches if team_id in (m.home_team_id, m.away_team_id)]
        return self._to_views(matches)

    def get(self, match_id: UUID) -> Match:
        match = self.repos.matches.get(match_id)
        if match is None:
            raise NotFoundError("Partido", match_id)
        return match

    def get_view(self, match_id: UUID) -> MatchView:
        return self._to_views([self.get(match_id)])[0]

    def referee_sheet(self, match_id: UUID) -> RefereeSheet:
        """Cedula de referees: los dos equipos con sus jugadores activos (por numero)."""
        match = self.get_view(match_id)
        tournament = self.tournaments.get(match.tournament_id)
        teams = {t.id: t for t in self.repos.teams.list(in_filters={"id": [match.home_team_id, match.away_team_id]})}

        def sheet_team(team_id: UUID) -> RefereeSheetTeam:
            team = teams[team_id]
            players = self.repos.players.list(filters={"club_id": team.club_id, "is_active": True},
                                              order_by=["jersey_number", "full_name"])
            return RefereeSheetTeam(
                name=team.name,
                players=[RefereeSheetPlayer(jersey_number=p.jersey_number, full_name=p.full_name) for p in players],
            )

        return RefereeSheet(
            tournament_name=tournament.name,
            category=tournament.category,
            round=match.round,
            scheduled_at=match.scheduled_at,
            venue=match.venue,
            home=sheet_team(match.home_team_id),
            away=sheet_team(match.away_team_id),
        )

    # ------------------------------------------------------------ escritura
    def create(self, tournament_id: UUID, data: MatchCreate) -> MatchView:
        self.tournaments.get(tournament_id)
        payload = self._validated(tournament_id, data.model_dump())
        match = self.repos.matches.create({**payload, "tournament_id": tournament_id})
        return self._to_views([match])[0]

    def update(self, match_id: UUID, data: MatchUpdate) -> MatchView:
        return self._apply(match_id, data.changes())

    def set_result(self, match_id: UUID, data: MatchResult) -> MatchView:
        """Captura o corrige el marcador; la tabla de posiciones se recalcula sola."""
        return self._apply(match_id, data.changes() | {"status": data.status})

    def delete(self, match_id: UUID) -> None:
        if not self.repos.matches.delete(match_id):
            raise NotFoundError("Partido", match_id)

    # ------------------------------------------------------------ reglas
    def _apply(self, match_id: UUID, changes: dict[str, Any]) -> MatchView:
        match = self.get(match_id)
        if not changes:
            return self._to_views([match])[0]
        validated = self._validated(match.tournament_id, match.model_dump() | changes)
        updated = self.repos.matches.update(match_id, validated) or match
        return self._to_views([updated])[0]

    def _validated(self, tournament_id: UUID, state: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "round_id", "home_team_id", "away_team_id", "scheduled_at", "venue",
            "status", "home_score", "away_score", "forfeit_loser_team_id", "notes",
        )
        data = {k: state.get(k) for k in fields}
        home, away = data["home_team_id"], data["away_team_id"]
        if home == away:
            raise ValidationError("Un equipo no puede jugar contra si mismo")

        teams = self.repos.teams.list(in_filters={"id": [home, away]})
        if len([t for t in teams if t.tournament_id == tournament_id]) != 2:
            raise ValidationError("Ambos equipos deben pertenecer al torneo")

        if data["round_id"]:
            round_ = self.repos.rounds.get(data["round_id"])
            if round_ is None or round_.tournament_id != tournament_id:
                raise ValidationError("La jornada no pertenece al torneo")

        status = MatchStatus(data["status"])
        if status == MatchStatus.FINISHED:
            if data["home_score"] is None or data["away_score"] is None:
                raise ValidationError("Un partido finalizado requiere el marcador de ambos equipos")
            if data["home_score"] == data["away_score"]:
                raise ValidationError("No hay empates: captura el marcador final incluyendo el tiempo extra")
        if status == MatchStatus.FORFEIT:
            if data["forfeit_loser_team_id"] not in (home, away):
                raise ValidationError("Indica en forfeit_loser_team_id que equipo pierde por forfeit")
            data["home_score"], data["away_score"] = forfeit_scores(home, data["forfeit_loser_team_id"])
        else:
            data["forfeit_loser_team_id"] = None
        return data

    def _to_views(self, matches: list[Match]) -> list[MatchView]:
        if not matches:
            return []
        team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
        round_ids = {m.round_id for m in matches if m.round_id}
        teams = {t.id: TeamSummary.model_validate(t, from_attributes=True)
                 for t in self.repos.teams.list(in_filters={"id": list(team_ids)})}
        rounds = {r.id: RoundSummary.model_validate(r, from_attributes=True)
                  for r in self.repos.rounds.list(in_filters={"id": list(round_ids)})} if round_ids else {}
        return [
            MatchView(
                **m.model_dump(),
                home_team=teams.get(m.home_team_id),
                away_team=teams.get(m.away_team_id),
                round=rounds.get(m.round_id) if m.round_id else None,
                winner_team_id=winner_team_id(m),
            )
            for m in matches
        ]
