from uuid import uuid4

from app.domain.entities import Match, StandingAdjustment, Team, Tournament
from app.domain.enums import MatchStatus
from app.domain.standings import compute_standings


def _setup():
    tournament = Tournament(id=uuid4(), name="Apertura")  # 2 / 1 / 0 puntos
    toros, lobos, snakes = (Team(id=uuid4(), tournament_id=tournament.id, name=n) for n in ("TOROS", "LOBOS", "SNAKES"))
    return tournament, toros, lobos, snakes


def _match(home, away, hs, as_, status=MatchStatus.FINISHED, loser=None):
    return Match(id=uuid4(), tournament_id=home.tournament_id, home_team_id=home.id, away_team_id=away.id,
                 home_score=hs, away_score=as_, status=status, forfeit_loser_team_id=loser)


def test_basic_table_like_rol_de_juegos():
    t, toros, lobos, snakes = _setup()
    matches = [
        _match(lobos, toros, 0, 32),     # Lobos Plateados 0 vs Toros 32 (J1)
        _match(toros, snakes, 27, 6),    # Toros 27 vs Snakes 6
        _match(lobos, snakes, 0, 21),    # Lobos 0 vs Snakes 21
    ]
    table = compute_standings(t, [toros, lobos, snakes], matches)

    assert [r.team_name for r in table] == ["TOROS", "SNAKES", "LOBOS"]
    first = table[0]
    assert (first.played, first.won, first.lost, first.points_for, first.points_against) == (2, 2, 0, 59, 6)
    assert first.point_difference == 53
    assert first.points == 4
    assert table[2].points == 0 and table[2].lost == 2


def test_cancelled_and_scheduled_do_not_count():
    t, toros, lobos, snakes = _setup()
    matches = [
        _match(toros, lobos, None, None, status=MatchStatus.CANCELLED),  # "SE CANCELO POR LLUVIA"
        _match(toros, snakes, None, None, status=MatchStatus.SCHEDULED),
        _match(toros, snakes, None, None, status=MatchStatus.POSTPONED),
    ]
    table = compute_standings(t, [toros, lobos, snakes], matches)
    assert all(r.played == 0 and r.points == 0 for r in table)


def test_forfeit_loser_loses_regardless_of_score():
    t, toros, lobos, snakes = _setup()
    # "TOROS 21 VS TUCANES 0 - PIERDE TUCANES POR FORFIET"
    table = compute_standings(t, [toros, lobos], [_match(lobos, toros, 0, 0, MatchStatus.FORFEIT, loser=lobos.id)])
    by_name = {r.team_name: r for r in table}
    assert by_name["TOROS"].won == 1 and by_name["TOROS"].points == 2
    assert by_name["LOBOS"].lost == 1


def test_draw_and_adjustments():
    t, toros, lobos, snakes = _setup()
    adjustments = [StandingAdjustment(id=uuid4(), tournament_id=t.id, team_id=lobos.id, points=-1, reason="Multa")]
    table = compute_standings(t, [toros, lobos], [_match(toros, lobos, 14, 14)], adjustments)
    by_name = {r.team_name: r for r in table}
    assert by_name["TOROS"].drawn == 1 and by_name["TOROS"].points == 1
    assert by_name["LOBOS"].points == 0 and by_name["LOBOS"].adjustment_reasons == ["Multa"]


def test_tiebreak_by_point_difference_then_points_for():
    t, toros, lobos, snakes = _setup()
    matches = [_match(toros, snakes, 40, 10), _match(lobos, snakes, 20, 10), _match(snakes, toros, 30, 0)]
    table = compute_standings(t, [toros, lobos, snakes], matches)
    # Toros y Snakes: 2 pts; Toros dif 40-40=0 ... Snakes dif (10+10+30)-(40+20+0)=-10; Lobos 2 pts dif +10
    assert [r.team_name for r in table] == ["LOBOS", "TOROS", "SNAKES"]


def test_custom_points_config():
    t, toros, lobos, _ = _setup()
    t = t.model_copy(update={"points_win": 3, "points_loss": 1})
    table = compute_standings(t, [toros, lobos], [_match(toros, lobos, 20, 6)])
    assert [r.points for r in table] == [3, 1]
