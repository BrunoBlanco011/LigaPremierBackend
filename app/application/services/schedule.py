from datetime import timedelta
from uuid import UUID

from app.application.dto import ScheduleGenerate
from app.application.read_models import ScheduleResult
from app.application.services.tournaments import TournamentService
from app.core.exceptions import ConflictError, ValidationError
from app.domain.enums import MatchStatus
from app.domain.repositories import Repositories
from app.domain.scheduling import round_robin


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
        rounds = self.repos.rounds.create_many([
            {
                "tournament_id": tournament_id,
                "number": plan.number,
                "name": f"Jornada {plan.number}",
                "start_date": (
                    data.start_date + timedelta(days=(plan.number - 1) * data.days_between_rounds)
                    if data.start_date else None
                ),
                "bye_team_id": plan.bye_team_id,
            }
            for plan in plans
        ])
        round_ids = {r.number: r.id for r in rounds}
        matches = self.repos.matches.create_many([
            {
                "tournament_id": tournament_id,
                "round_id": round_ids[plan.number],
                "home_team_id": fixture.home_team_id,
                "away_team_id": fixture.away_team_id,
                "status": MatchStatus.SCHEDULED,
            }
            for plan in plans
            for fixture in plan.fixtures
        ])
        return ScheduleResult(rounds_created=len(rounds), matches_created=len(matches))

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
