from uuid import UUID

from app.application.dto import AdjustmentCreate, AdjustmentUpdate
from app.application.read_models import StandingView, TeamSummary
from app.application.services.tournaments import TournamentService
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.entities import StandingAdjustment
from app.domain.repositories import Repositories
from app.domain.standings import compute_standings


class StandingsService:
    """La tabla se calcula siempre a partir de los partidos: nunca se desincroniza.

    Para corregirla, el admin edita el resultado del partido o registra un
    ajuste manual de puntos (multa, sancion, bonificacion) con su motivo.
    """

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.tournaments = TournamentService(repos)

    def get_standings(self, tournament_id: UUID) -> list[StandingView]:
        tournament = self.tournaments.get(tournament_id)
        teams = self.repos.teams.list(filters={"tournament_id": tournament_id})
        matches = self.repos.matches.list(filters={"tournament_id": tournament_id})
        adjustments = self.repos.adjustments.list(filters={"tournament_id": tournament_id})
        rows = compute_standings(tournament, teams, matches, adjustments)
        return [
            StandingView(
                position=r.position,
                team=TeamSummary(id=r.team_id, name=r.team_name, logo_url=r.logo_url),
                played=r.played,
                won=r.won,
                drawn=r.drawn,
                lost=r.lost,
                points_for=r.points_for,
                points_against=r.points_against,
                point_difference=r.point_difference,
                adjustment_points=r.adjustment_points,
                adjustment_reasons=r.adjustment_reasons,
                points=r.points,
            )
            for r in rows
        ]

    # ------------------------------------------------------------ ajustes
    def list_adjustments(self, tournament_id: UUID) -> list[StandingAdjustment]:
        self.tournaments.get(tournament_id)
        return self.repos.adjustments.list(filters={"tournament_id": tournament_id}, order_by=["-created_at"])

    def create_adjustment(self, tournament_id: UUID, data: AdjustmentCreate) -> StandingAdjustment:
        self.tournaments.get(tournament_id)
        team = self.repos.teams.get(data.team_id)
        if team is None or team.tournament_id != tournament_id:
            raise ValidationError("El equipo no pertenece al torneo")
        return self.repos.adjustments.create({**data.model_dump(), "tournament_id": tournament_id})

    def update_adjustment(self, adjustment_id: UUID, data: AdjustmentUpdate) -> StandingAdjustment:
        current = self.repos.adjustments.get(adjustment_id)
        if current is None:
            raise NotFoundError("Ajuste", adjustment_id)
        changes = data.changes()
        if not changes:
            return current
        return self.repos.adjustments.update(adjustment_id, changes) or current

    def delete_adjustment(self, adjustment_id: UUID) -> None:
        if not self.repos.adjustments.delete(adjustment_id):
            raise NotFoundError("Ajuste", adjustment_id)
