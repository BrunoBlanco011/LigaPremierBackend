"""Generacion del rol de juegos "todos contra todos" (metodo del circulo).

Con N equipos se generan N-1 jornadas (N par) o N jornadas (N impar, un
equipo descansa -BYE- en cada jornada). Cada equipo enfrenta exactamente una
vez a cada rival; con `double_round=True` se juega ida y vuelta invirtiendo
local y visitante.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Fixture:
    home_team_id: UUID
    away_team_id: UUID


@dataclass(frozen=True)
class RoundPlan:
    number: int
    fixtures: list[Fixture]
    bye_team_id: UUID | None = None


def round_robin(team_ids: list[UUID], double_round: bool = False) -> list[RoundPlan]:
    if len(team_ids) < 2:
        return []
    slots: list[UUID | None] = list(team_ids)
    if len(slots) % 2:
        slots.append(None)  # None = descansa

    n = len(slots)
    plans: list[RoundPlan] = []
    for index in range(n - 1):
        fixtures: list[Fixture] = []
        bye: UUID | None = None
        for i in range(n // 2):
            a, b = slots[i], slots[n - 1 - i]
            if a is None or b is None:
                bye = a or b
                continue
            # Localia balanceada: el equipo fijo alterna cada jornada; en los demas
            # pares la rotacion del circulo ya reparte la localia
            if i == 0:
                home, away = (a, b) if index % 2 == 0 else (b, a)
            else:
                home, away = a, b
            fixtures.append(Fixture(home, away))
        plans.append(RoundPlan(number=index + 1, fixtures=fixtures, bye_team_id=bye))
        # Rotacion: el primer lugar queda fijo, los demas giran
        slots = [slots[0], slots[-1], *slots[1:-1]]

    if double_round:
        first_leg = len(plans)
        plans += [
            RoundPlan(
                number=first_leg + p.number,
                fixtures=[Fixture(f.away_team_id, f.home_team_id) for f in p.fixtures],
                bye_team_id=p.bye_team_id,
            )
            for p in plans
        ]
    return plans
