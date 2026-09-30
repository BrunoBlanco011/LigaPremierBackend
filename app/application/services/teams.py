from uuid import UUID

from app.application.dto import TeamRegister
from app.application.services.tournaments import TournamentService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.entities import Team
from app.domain.repositories import Repositories


class TeamService:
    """Inscripciones: un equipo es un club inscrito a un torneo."""

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self.tournaments = TournamentService(repos)

    def list_by_tournament(self, tournament_id: UUID) -> list[Team]:
        self.tournaments.get(tournament_id)
        return self.repos.teams.list(filters={"tournament_id": tournament_id}, order_by=["name"])

    def get(self, team_id: UUID) -> Team:
        team = self.repos.teams.get(team_id)
        if team is None:
            raise NotFoundError("Equipo", team_id)
        return team

    def register(self, tournament_id: UUID, data: TeamRegister) -> list[Team]:
        self.tournaments.get(tournament_id)
        club_ids = list(dict.fromkeys(data.club_ids))
        found = {c.id for c in self.repos.clubs.list(in_filters={"id": club_ids})}
        missing = [str(cid) for cid in club_ids if cid not in found]
        if missing:
            raise ValidationError(f"Clubes no encontrados: {', '.join(missing)}")

        registered = {t.club_id for t in self.repos.teams.list(filters={"tournament_id": tournament_id})}
        already = [cid for cid in club_ids if cid in registered]
        if already:
            names = [t.name for t in self.repos.teams.list(filters={"tournament_id": tournament_id})
                     if t.club_id in already]
            raise ConflictError(f"Ya estan inscritos en el torneo: {', '.join(names)}")

        return self.repos.teams.create_many(
            [{"tournament_id": tournament_id, "club_id": cid} for cid in club_ids]
        )

    def unregister(self, team_id: UUID) -> None:
        """Borra la inscripcion y, en cascada, sus partidos, estadisticas y finanzas de ese torneo."""
        self.get(team_id)
        self.repos.teams.delete(team_id)
