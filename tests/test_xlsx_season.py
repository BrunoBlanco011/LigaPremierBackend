"""Pruebas de volumen con la temporada real del archivo "ROL DE JUEGOS (1).xlsx".

12 equipos, ~190 jugadores, 11 jornadas mas partidos pendientes, forfeits,
cancelaciones por lluvia y adeudos. Todo pasa por la API (repositorios en memoria).
El xlsx no se versiona (trae nombres reales): sin el archivo estas pruebas se omiten.

Lo que la hoja trae inconsistente se corrige o simula con `xlsx_league.clean`
(dorsales repetidos, asistencias de mas y la tabla capturada a mano, que no cuadra);
`test_sheet_inconsistencies_are_cleaned` deja registro de cada correccion.
"""

import unittest
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import cache
from itertools import combinations
from zoneinfo import ZoneInfo

from tests import xlsx_league
from tests.helpers import Env

API = "/api/v1"
STATS = ("touchdowns", "td_passes", "interceptions", "sacks", "tackles")


@cache
def raw_league() -> xlsx_league.League:
    if not xlsx_league.available():
        raise unittest.SkipTest(f"No esta {xlsx_league.XLSX_PATH.name}")
    return xlsx_league.load()


@cache
def cleaned() -> tuple[xlsx_league.League, tuple[str, ...]]:
    league, fixes = xlsx_league.clean(raw_league())
    return league, tuple(fixes)


def league() -> xlsx_league.League:
    return cleaned()[0]


class Season:
    """Carga la temporada por la API, paso a paso."""

    def __init__(self) -> None:
        self.lg = league()
        self.env = Env()
        self.c, self.h = self.env.client, self.env.as_admin
        self.t = self.env.tournament(name="Liga Premier 2026")
        self.team = {name: self.env.team(self.t["id"], name)["id"] for name in self.lg.teams}
        teams = self.c.get(f"{API}/tournaments/{self.t['id']}/teams").json()
        self.club = {t["name"]: t["club_id"] for t in teams}
        self.players: dict[str, list[tuple[xlsx_league.SheetPlayer, dict]]] = {}
        self.matches: list[tuple[xlsx_league.SheetMatch, dict]] = []

    def url(self, path: str) -> str:
        return f"{API}/tournaments/{self.t['id']}/{path}"

    def load_rosters(self) -> None:
        for team, roster in self.lg.rosters.items():
            self.players[team] = []
            for p in roster:
                body = {"full_name": p.full_name, "jersey_number": p.jersey_number}
                r = self.c.post(f"{API}/clubs/{self.club[team]}/players", json=body, headers=self.h)
                assert r.status_code == 201, r.text
                self.players[team].append((p, r.json()))

    def load_results(self) -> None:
        rounds = {}
        for n in sorted({m.round_number for m in self.lg.matches if m.round_number}):
            r = self.c.post(self.url("rounds"), json={"number": n}, headers=self.h)
            rounds[n] = r.json()["id"]
        for m in self.lg.matches:
            body = {"home_team_id": self.team[m.home], "away_team_id": self.team[m.away],
                    "round_id": rounds.get(m.round_number), "status": m.status}
            if m.status == "finished":
                body |= {"home_score": m.home_score, "away_score": m.away_score}
            elif m.status == "forfeit":
                body |= {"forfeit_loser_team_id": self.team[m.forfeit_loser]}
            r = self.c.post(self.url("matches"), json=body, headers=self.h)
            assert r.status_code == 201, r.text
            self.matches.append((m, r.json()))

    def load_stats(self) -> None:
        """La hoja solo trae totales: cada jugador asiste a los primeros N partidos de su
        equipo (N = su asistencia) y sus numeros se reparten entre esos partidos."""
        played = [(m, api) for m, api in self.matches if m.status in ("finished", "forfeit")]
        lines: dict[str, list[dict]] = defaultdict(list)
        for team, roster in self.players.items():
            team_matches = [api["id"] for m, api in played if team in (m.home, m.away)]
            for p, player in roster:
                attended = team_matches[: p.games_attended]
                for i, match_id in enumerate(attended):
                    line = {"player_id": player["id"], "attended": True}
                    for stat in STATS:
                        q, rem = divmod(getattr(p, stat), len(attended))
                        line[stat] = q + (1 if i < rem else 0)
                    lines[match_id].append(line)
        for match_id, sheet in lines.items():
            r = self.c.put(f"{API}/matches/{match_id}/stats", json=sheet, headers=self.h)
            assert r.status_code == 200, r.text

    def standings(self) -> dict[str, dict]:
        return {row["team"]["name"]: row for row in self.c.get(self.url("standings")).json()}


# ------------------------------------------------------------------ datos de la hoja
def test_sheet_inconsistencies_are_cleaned():
    fixes = cleaned()[1]
    assert sum("repetido" in f for f in fixes) == 10
    assert [f for f in fixes if "asistencia" in f] == ["DOLPHINS: asistencia 12 > 11 partidos -> 11"]
    # Tabla a mano: 7 renglones no cuadran con los resultados
    assert sum(f.startswith("tabla ") for f in fixes) == 7

    sheet = raw_league().standings
    assert sum(r.played for r in sheet) % 2 == 1  # imposible: cada partido suma 2 juegos
    assert sum(r.points_for for r in sheet) != sum(r.points_against for r in sheet)


def test_duplicate_jersey_in_club_is_rejected():
    s = Season()
    team, roster = next((t, r) for t, r in raw_league().rosters.items() if t == "LOBOS PLATEADOS")
    url = f"{API}/clubs/{s.club[team]}/players"
    codes = [s.c.post(url, json={"full_name": p.full_name, "jersey_number": p.jersey_number},
                      headers=s.h).status_code for p in roster]
    assert codes.count(409) == 4 and codes.count(201) == len(roster) - 4


# ------------------------------------------------------------------ plantillas
def test_rosters_from_sheet():
    s = Season()
    s.load_rosters()
    lg = s.lg

    assert sum(len(r) for r in lg.rosters.values()) == 191
    for team, roster in lg.rosters.items():
        players = s.c.get(f"{API}/clubs/{s.club[team]}/players").json()
        assert len(players) == len(roster), team
        assert len({p["jersey_number"] for p in players if p["jersey_number"] is not None}) == len(
            [p for p in players if p["jersey_number"] is not None]), team


# ------------------------------------------------------------------ rol de juegos
def test_generate_schedule_for_the_12_real_teams():
    s = Season()
    body = {"start_date": "2026-05-18", "weekdays": [0, 2], "start_time": "19:00",
            "match_duration_minutes": 60, "max_matches_per_day": 3, "venue": "Campo Liga Premier"}
    r = s.c.post(s.url("schedule/generate"), json=body, headers=s.h)
    assert r.json() == {"rounds_created": 11, "matches_created": 66}

    rounds = s.c.get(s.url("rounds")).json()
    matches = s.c.get(s.url("matches")).json()
    assert all(r["bye_team_id"] is None for r in rounds)  # 12 equipos: nadie descansa

    # Todos contra todos: los 66 cruces posibles, una sola vez
    pairs = Counter(frozenset((m["home_team_id"], m["away_team_id"])) for m in matches)
    assert set(pairs) == {frozenset(p) for p in combinations(s.team.values(), 2)}
    assert set(pairs.values()) == {1}

    # Cada equipo juega una vez por jornada y la localia queda repartida (5 o 6 de 11)
    by_round = defaultdict(list)
    home_games = Counter(m["home_team_id"] for m in matches)
    for m in matches:
        by_round[m["round_id"]] += [m["home_team_id"], m["away_team_id"]]
    assert all(sorted(teams) == sorted(s.team.values()) for teams in by_round.values())
    assert set(home_games.values()) <= {5, 6}

    # Como en la hoja: cada jornada es lunes y miercoles de la misma semana, 3 partidos por dia
    spans = [(date.fromisoformat(r["start_date"]), date.fromisoformat(r["end_date"])) for r in rounds]
    assert spans[0] == (date(2026, 5, 18), date(2026, 5, 20))
    assert all((a.weekday(), b.weekday(), (b - a).days) == (0, 2, 2) for a, b in spans)
    assert all(b2 - b1 == timedelta(weeks=1) for (b1, _), (b2, _) in zip(spans, spans[1:]))
    tournament = s.c.get(f"{API}/tournaments/{s.t['id']}").json()
    assert (tournament["start_date"], tournament["end_date"]) == ("2026-05-18", "2026-07-29")

    # 19:00, 20:00 y 21:00 hora de Ciudad de Mexico cada dia
    mx = ZoneInfo("America/Mexico_City")
    kickoffs = Counter()
    for m in matches:
        local = datetime.fromisoformat(m["scheduled_at"]).astimezone(mx)
        kickoffs[(local.weekday(), local.hour)] += 1
    assert kickoffs == {(day, hour): 11 for day in (0, 2) for hour in (19, 20, 21)}
    assert {m["venue"] for m in matches} == {"Campo Liga Premier"}


# ------------------------------------------------------------------ tabla
def test_standings_from_real_results():
    s = Season()
    s.load_results()
    lg, table = s.lg, s.standings()

    decided = [m for m in lg.matches if m.status in ("finished", "forfeit")]
    assert len(decided) == 66 and Counter(m.status for m in lg.matches) == {
        "finished": 62, "forfeit": 4, "cancelled": 3}

    # Invariantes que la tabla de la hoja no cumple
    rows = table.values()
    assert sum(r["won"] for r in rows) == sum(r["lost"] for r in rows) == len(decided)
    assert sum(r["points_for"] for r in rows) == sum(r["points_against"] for r in rows)
    assert all(r["points"] == 2 * r["won"] for r in rows)
    for team in lg.teams:  # los cancelados por lluvia no cuentan
        assert table[team]["played"] == sum(team in (m.home, m.away) for m in decided), team

    # Forfeits: el perdedor queda 0-21
    for m, api in s.matches:
        if m.status == "forfeit":
            loser_home = m.forfeit_loser == m.home
            assert (api["home_score"], api["away_score"]) == ((0, 21) if loser_home else (21, 0))

    # Renglon por renglon contra la tabla esperada (recalculada a mano de los resultados)
    keys = ("position", "played", "won", "lost", "points_for", "points_against", "points")
    for row in lg.standings:
        assert tuple(table[row.team][k] for k in keys) == tuple(getattr(row, k) for k in keys), row.team
    # Empate a 6 puntos entre CHARS, OLD STAR y TUNE SQUAD: desempata puntos a favor
    assert [t for t in table if table[t]["points"] == 6] == ["CHARS", "OLD STAR", "TUNE SQUAD"]

    # Corregir un resultado mueve la tabla al momento
    m, api = next((m, api) for m, api in s.matches if m.home == "DOLPHINS" and m.status == "finished")
    r = s.c.put(f"{API}/matches/{api['id']}/result",
                json={"home_score": m.home_score, "away_score": m.home_score + 1}, headers=s.h)
    assert r.status_code == 200, r.text
    assert s.standings()["DOLPHINS"]["lost"] == 1


# ------------------------------------------------------------------ estadisticas
def test_player_totals_and_leaders_from_sheet():
    s = Season()
    s.load_rosters()
    s.load_results()
    s.load_stats()

    totals = {t["player_id"]: t for t in s.c.get(s.url("player-stats"), params={"limit": 500}).json()}
    team_games = Counter()
    for m in s.lg.matches:
        if m.status in ("finished", "forfeit"):
            team_games[m.home] += 1
            team_games[m.away] += 1

    for team, roster in s.players.items():
        for p, player in roster:
            got = totals.get(player["id"])
            if p.games_attended == 0:
                # Sin asistencias sigue en la plantilla, en ceros
                assert got is None or all(got[k] == 0 for k in (*STATS, "games_attended"))
                continue
            for stat in STATS:
                assert got[stat] == getattr(p, stat), (team, stat)
            assert got["games_attended"] == p.games_attended <= team_games[team]

    sheet_players = [(team, p) for team, roster in s.players.items() for p, _ in roster]
    for stat in STATS:
        leaders = s.c.get(s.url("player-stats"), params={"sort_by": stat, "limit": 5}).json()
        best = max(getattr(p, stat) for _, p in sheet_players)
        assert leaders[0][stat] == best, stat
        assert [x[stat] for x in leaders] == sorted((x[stat] for x in leaders), reverse=True)
    league_totals = {stat: sum(getattr(p, stat) for _, p in sheet_players) for stat in STATS}
    assert {stat: sum(t[stat] for t in totals.values()) for stat in STATS} == league_totals


# ------------------------------------------------------------------ finanzas
def test_finance_balances_match_sheet():
    s = Season()
    fee = Decimal("1000")
    r = s.c.post(s.url("finance/registration-fees"), json={"amount": str(fee)}, headers=s.h)
    assert r.status_code == 201 and len(r.json()) == 12

    def move(team: str, kind: str, amount: Decimal, description: str) -> None:
        body = {"team_id": s.team[team], "type": kind, "amount": str(amount), "description": description}
        assert s.c.post(s.url("finance/movements"), json=body, headers=s.h).status_code == 201

    balances = {b.team: b for b in s.lg.balances}
    for team in s.lg.teams:
        b = balances.get(team) or xlsx_league.SheetBalance(team, 0, 0, 0, 0)
        if fee - b.registration_due:
            move(team, "payment", fee - b.registration_due, "Pago de inscripcion")
        if b.fines:
            move(team, "fine", Decimal(b.fines), "Multas")
        if b.payments:
            move(team, "payment", Decimal(b.payments), "Abonos")

    summary = s.c.get(s.url("finance/summary"), headers=s.h).json()
    got = {row["team"]["name"]: Decimal(row["balance"]) for row in summary["teams"]}
    assert got == {team: Decimal(balances[team].balance if team in balances else 0) for team in s.lg.teams}
    assert Decimal(summary["total_balance"]) == sum(Decimal(b.balance) for b in s.lg.balances) == 7300
