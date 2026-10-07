from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID

from app.application.dto import ScheduleGenerate
from app.application.read_models import ScheduleResult
from app.application.services.tournaments import TournamentService
from app.core.exceptions import ConflictError, ValidationError
from app.domain.enums import MatchStatus
from app.domain.repositories import Repositories
from app.domain.scheduling import round_days, round_robin


class ScheduleService:
    """Genera el rol de juegos: cada equipo enfrenta a todos los demas equipos del torneo."""

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.tournaments = TournamentService(repos)

    def generate(self, tournament_id: UUID, data: ScheduleGenerate) -> ScheduleResult:
        self.tournaments.get(tournament_id)
        teams = self.repos.teams.list(filters={"tournament_id": tournament_id}, order_by=["name"])
        if len(teams) < 2:
            raise ValidationError("Se necesitan al menos 2 equipos para generar el rol de juegos")

        self._clear_existing(tournament_id, data.replace_existing)

        plans = round_robin([t.id for t in teams], double_round=data.double_round)
        per_day = data.max_matches_per_day or max((len(p.fixtures) for p in plans), default=1) or 1
        days: list[list[date]] = (
            round_days(
                data.start_date,
                set(data.weekdays or [data.start_date.weekday()]),
                [max(1, -(-len(p.fixtures) // per_day)) for p in plans],
            )
            if data.start_date else [[] for _ in plans]
        )
        rounds = self.repos.rounds.create_many([
            {
                "tournament_id": tournament_id,
                "number": plan.number,
                "name": f"Jornada {plan.number}",
                "start_date": game_days[0] if game_days else None,
                "end_date": game_days[-1] if game_days else None,
                "bye_team_id": plan.bye_team_id,
            }
            for plan, game_days in zip(plans, days)
        ])
        round_ids = {r.number: r.id for r in rounds}
        matches = self.repos.matches.create_many([
            {
                "tournament_id": tournament_id,
                "round_id": round_ids[plan.number],
                "home_team_id": fixture.home_team_id,
                "away_team_id": fixture.away_team_id,
                "scheduled_at": self._kickoff(data, game_days[i // per_day] if game_days else None, i % per_day),
                "venue": data.venue or None,
                "status": MatchStatus.SCHEDULED,
            }
            for plan, game_days in zip(plans, days)
            for i, fixture in enumerate(plan.fixtures)
        ])
        self._set_tournament_dates(tournament_id, rounds)
        return ScheduleResult(rounds_created=len(rounds), matches_created=len(matches))

    @staticmethod
    def _kickoff(data: ScheduleGenerate, day: date | None, slot: int) -> datetime | None:
        """Los partidos de un mismo dia van uno tras otro desde la hora del primero."""
        if day is None or data.start_time is None:
            return None
        first = datetime.combine(day, data.start_time, tzinfo=ZoneInfo(data.timezone))
        return first + timedelta(minutes=slot * data.match_duration_minutes)

    def _set_tournament_dates(self, tournament_id: UUID, rounds: list) -> None:
        """El inicio y el fin del torneo los marcan la primera y la ultima jornada del rol."""
        dates = [d for r in rounds for d in (r.start_date, r.end_date) if d]
        if dates:
            self.repos.tournaments.update(tournament_id, {"start_date": min(dates), "end_date": max(dates)})

    def _clear_existing(self, tournament_id: UUID, replace: bool) -> None:
        matches = self.repos.matches.list(filters={"tournament_id": tournament_id})
        rounds = self.repos.rounds.list(filters={"tournament_id": tournament_id})
        if not matches and not rounds:
            return
        if not replace:
            raise ConflictError(
                "El torneo ya tiene jornadas o partidos. Envia replace_existing=true para reemplazarlos"
            )
        played = [m for m in matches if m.status.counts_for_standings or m.status == MatchStatus.IN_PROGRESS]
        if played:
            raise ConflictError("No se puede regenerar el rol: ya hay partidos jugados o en juego")
        for match in matches:
            self.repos.matches.delete(match.id)
        for round_ in rounds:
            self.repos.rounds.delete(round_.id)
