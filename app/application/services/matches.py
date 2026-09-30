from __future__ import annotations

from typing import Any
from uuid import UUID

from app.application.dto import MatchCreate, MatchResult, MatchUpdate
from app.application.read_models import MatchView, RoundSummary, TeamSummary
from app.application.services.tournaments import TournamentService
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.entities import Match
from app.domain.enums import MatchStatus
from app.domain.repositories import Repositories
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
        if status == MatchStatus.FINISHED and (data["home_score"] is None or data["away_score"] is None):
            raise ValidationError("Un partido finalizado requiere el marcador de ambos equipos")
        if status == MatchStatus.FORFEIT:
            if data["forfeit_loser_team_id"] not in (home, away):
                raise ValidationError("Indica en forfeit_loser_team_id que equipo pierde por forfeit")
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
