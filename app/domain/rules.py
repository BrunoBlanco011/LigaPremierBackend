"""Reglas fijas del reglamento de la liga."""

from uuid import UUID

# Un equipo que pierde por forfeit pierde 21-0
FORFEIT_WINNER_SCORE = 21
FORFEIT_LOSER_SCORE = 0


def forfeit_scores(home_team_id: UUID, loser_team_id: UUID) -> tuple[int, int]:
    """Marcador (local, visitante) de un partido perdido por forfeit."""
    if loser_team_id == home_team_id:
        return FORFEIT_LOSER_SCORE, FORFEIT_WINNER_SCORE
    return FORFEIT_WINNER_SCORE, FORFEIT_LOSER_SCORE
