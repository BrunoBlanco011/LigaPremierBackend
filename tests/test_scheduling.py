from datetime import date
from itertools import combinations
from uuid import uuid4

from app.domain.scheduling import round_dates, round_robin


def _check(n: int) -> None:
    teams = [uuid4() for _ in range(n)]
    plans = round_robin(teams)
    assert len(plans) == (n - 1 if n % 2 == 0 else n)

    pairs = sorted(sorted(map(str, (f.home_team_id, f.away_team_id))) for p in plans for f in p.fixtures)
    expected = sorted(sorted(map(str, pair)) for pair in combinations(teams, 2))
    assert pairs == expected  # cada equipo contra todos, exactamente una vez

    for plan in plans:  # nadie juega dos veces en la misma jornada
        playing = [t for f in plan.fixtures for t in (f.home_team_id, f.away_team_id)]
        assert len(playing) == len(set(playing))
        assert (plan.bye_team_id is None) == (n % 2 == 0)

    homes = [sum(1 for p in plans for f in p.fixtures if f.home_team_id == t) for t in teams]
    assert max(homes) - min(homes) <= 1  # localia balanceada


def test_round_robin_even_and_odd():
    for n in range(2, 15):
        _check(n)


def test_double_round_inverts_home_and_away():
    teams = [uuid4() for _ in range(4)]
    plans = round_robin(teams, double_round=True)
    assert len(plans) == 6
    first, second = plans[0].fixtures[0], plans[3].fixtures[0]
    assert (first.home_team_id, first.away_team_id) == (second.away_team_id, second.home_team_id)


def test_less_than_two_teams():
    assert round_robin([]) == [] and round_robin([uuid4()]) == []


def test_round_dates_one_or_more_weekdays():
    monday = date(2026, 5, 18)
    assert round_dates(monday, {6}, 3) == [date(2026, 5, 24), date(2026, 5, 31), date(2026, 6, 7)]  # domingos
    assert round_dates(monday, {5, 6}, 3) == [date(2026, 5, 23), date(2026, 5, 24), date(2026, 5, 30)]  # sab y dom
    assert round_dates(monday, {0}, 2) == [monday, date(2026, 5, 25)]  # incluye el dia de inicio
