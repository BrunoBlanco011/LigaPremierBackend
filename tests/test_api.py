from tests.helpers import Env

API = "/api/v1"


# ------------------------------------------------------------ permisos
def test_public_can_read_but_not_write():
    env = Env()
    t = env.tournament()
    assert env.client.get(f"{API}/tournaments").status_code == 200
    assert env.client.get(f"{API}/tournaments/{t['id']}/standings").status_code == 200
    assert env.client.post(f"{API}/tournaments", json={"name": "X"}).status_code == 401
    assert env.client.post(f"{API}/tournaments", json={"name": "X"}, headers=env.as_coach).status_code == 403


def test_tournament_crud():
    env = Env()
    t = env.tournament(season="2026", points_win=2)
    r = env.client.patch(f"{API}/tournaments/{t['id']}", json={"status": "active"}, headers=env.as_admin)
    assert r.status_code == 200 and r.json()["status"] == "active"
    r = env.client.patch(f"{API}/tournaments/{t['id']}", json={"start_date": "2026-05-18", "end_date": "2026-05-01"},
                         headers=env.as_admin)
    assert r.status_code == 422
    assert env.client.delete(f"{API}/tournaments/{t['id']}", headers=env.as_admin).status_code == 204
    assert env.client.get(f"{API}/tournaments/{t['id']}").status_code == 404


# ------------------------------------------------------------ equipos
def test_team_unique_name_and_coach_assignment():
    env = Env()
    t = env.tournament()
    env.team(t["id"], "TOROS", coach_name="Rafa")
    r = env.client.post(f"{API}/tournaments/{t['id']}/teams", json={"name": "toros"}, headers=env.as_admin)
    assert r.status_code == 409

    r = env.client.post(f"{API}/tournaments/{t['id']}/teams",
                        json={"name": "LOBOS", "coach_user_id": str(env.admin.id)}, headers=env.as_admin)
    assert r.status_code == 422  # el usuario asignado debe ser coach

    lobos = env.team(t["id"], "LOBOS", coach_user_id=str(env.coach.id))
    mine = env.client.get(f"{API}/me/teams", headers=env.as_coach).json()
    assert [x["id"] for x in mine] == [lobos["id"]]


def test_logo_upload():
    env = Env()
    t = env.tournament()
    team = env.team(t["id"], "TOROS")
    files = {"file": ("logo.png", b"\x89PNG fake", "image/png")}
    r = env.client.post(f"{API}/teams/{team['id']}/logo", files=files, headers=env.as_admin)
    assert r.status_code == 200, r.text
    assert r.json()["logo_url"].startswith("https://cdn.test/")
    bad = {"file": ("logo.gif", b"GIF", "image/gif")}
    assert env.client.post(f"{API}/teams/{team['id']}/logo", files=bad, headers=env.as_admin).status_code == 422


# ------------------------------------------------------------ jugadores / coach
def test_coach_manages_only_own_team_players():
    env = Env()
    t = env.tournament()
    mine = env.team(t["id"], "LOBOS", coach_user_id=str(env.coach.id))
    other = env.team(t["id"], "TOROS")

    r = env.client.post(f"{API}/teams/{mine['id']}/players",
                        json={"full_name": "Marcos Rincon", "jersey_number": 17},
                        headers=env.as_coach)
    assert r.status_code == 201, r.text
    player = r.json()

    dup = env.client.post(f"{API}/teams/{mine['id']}/players", json={"full_name": "Otro", "jersey_number": 17},
                          headers=env.as_coach)
    assert dup.status_code == 409

    forbidden = env.client.post(f"{API}/teams/{other['id']}/players", json={"full_name": "X"}, headers=env.as_coach)
    assert forbidden.status_code == 403

    r = env.client.patch(f"{API}/players/{player['id']}", json={"jersey_number": 7}, headers=env.as_coach)
    assert r.status_code == 200 and r.json()["jersey_number"] == 7

    # Una baja deja de verse en el roster publico, pero el coach la sigue viendo
    env.client.patch(f"{API}/players/{player['id']}", json={"is_active": False}, headers=env.as_coach)
    assert env.client.get(f"{API}/teams/{mine['id']}/players").json() == []
    assert len(env.client.get(f"{API}/teams/{mine['id']}/players", headers=env.as_coach).json()) == 1

    # Solo nombre y numero: otros campos se rechazan
    extra = env.client.post(f"{API}/teams/{mine['id']}/players", json={"full_name": "X", "birth_date": "2000-01-01"},
                            headers=env.as_coach)
    assert extra.status_code == 422

    assert env.client.delete(f"{API}/players/{player['id']}", headers=env.as_coach).status_code == 204


# ------------------------------------------------------------ jornadas y partidos
def test_rounds_and_match_validation():
    env = Env()
    t = env.tournament()
    t2 = env.tournament(name="Otro torneo")
    toros, lobos = env.team(t["id"], "TOROS"), env.team(t["id"], "LOBOS")
    foreign = env.team(t2["id"], "SNAKES")

    r = env.client.post(f"{API}/tournaments/{t['id']}/rounds", json={"number": 1, "start_date": "2026-05-18"},
                        headers=env.as_admin)
    assert r.status_code == 201 and r.json()["name"] == "Jornada 1"
    round_id = r.json()["id"]
    assert env.client.post(f"{API}/tournaments/{t['id']}/rounds", json={"number": 1},
                           headers=env.as_admin).status_code == 409

    bad = [
        {"home_team_id": toros["id"], "away_team_id": toros["id"]},
        {"home_team_id": toros["id"], "away_team_id": foreign["id"]},
        {"home_team_id": toros["id"], "away_team_id": lobos["id"], "status": "finished"},
        {"home_team_id": toros["id"], "away_team_id": lobos["id"], "status": "forfeit"},
    ]
    for body in bad:
        r = env.client.post(f"{API}/tournaments/{t['id']}/matches", json=body, headers=env.as_admin)
        assert r.status_code == 422, body

    m = env.match(t["id"], lobos["id"], toros["id"], round_id=round_id, scheduled_at="2026-05-18T19:00:00-06:00")
    assert m["home_team"]["name"] == "LOBOS" and m["round"]["number"] == 1
    listed = env.client.get(f"{API}/tournaments/{t['id']}/matches", params={"team_id": toros["id"]}).json()
    assert len(listed) == 1


def test_result_updates_standings_and_can_be_corrected():
    env = Env()
    t = env.tournament()
    toros, lobos = env.team(t["id"], "TOROS"), env.team(t["id"], "LOBOS")
    m = env.match(t["id"], lobos["id"], toros["id"])

    r = env.client.put(f"{API}/matches/{m['id']}/result", json={"home_score": 0, "away_score": 32},
                       headers=env.as_admin)
    assert r.status_code == 200 and r.json()["winner_team_id"] == toros["id"]
    table = env.client.get(f"{API}/tournaments/{t['id']}/standings").json()
    assert table[0]["team"]["name"] == "TOROS" and table[0]["points"] == 2

    # Correccion del resultado -> la tabla se recalcula
    env.client.put(f"{API}/matches/{m['id']}/result", json={"home_score": 40, "away_score": 32},
                   headers=env.as_admin)
    table = env.client.get(f"{API}/tournaments/{t['id']}/standings").json()
    assert table[0]["team"]["name"] == "LOBOS"

    # No hay empates
    r = env.client.put(f"{API}/matches/{m['id']}/result", json={"home_score": 20, "away_score": 20},
                       headers=env.as_admin)
    assert r.status_code == 422

    # Forfeit: el marcador se fija en 21-0 sin importar lo que se envie
    r = env.client.put(f"{API}/matches/{m['id']}/result",
                       json={"status": "forfeit", "forfeit_loser_team_id": lobos["id"]}, headers=env.as_admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["winner_team_id"] == toros["id"] and (body["home_score"], body["away_score"]) == (0, 21)

    # Volver a 'finished' limpia el perdedor por forfeit
    r = env.client.patch(f"{API}/matches/{m['id']}", json={"status": "finished"}, headers=env.as_admin)
    assert r.json()["forfeit_loser_team_id"] is None

    # Ajuste manual
    r = env.client.post(f"{API}/tournaments/{t['id']}/standings/adjustments",
                        json={"team_id": toros["id"], "points": -2, "reason": "Adeudo de arbitraje"},
                        headers=env.as_admin)
    assert r.status_code == 201
    table = {row["team"]["name"]: row for row in env.client.get(f"{API}/tournaments/{t['id']}/standings").json()}
    assert table["TOROS"]["points"] == 0 and table["TOROS"]["adjustment_reasons"] == ["Adeudo de arbitraje"]


# ------------------------------------------------------------ estadisticas
def test_player_stats_capture_and_leaders():
    env = Env()
    t = env.tournament()
    toros, lobos = env.team(t["id"], "TOROS"), env.team(t["id"], "LOBOS")
    outsider_team = env.team(t["id"], "SNAKES")

    def player(team, name, n):
        r = env.client.post(f"{API}/teams/{team['id']}/players", json={"full_name": name, "jersey_number": n},
                            headers=env.as_admin)
        return r.json()

    rafa = player(toros, "Rafael Mendoza", 32)
    marcos = player(lobos, "Marcos Rincon", 17)
    outsider = player(outsider_team, "Kevin Luna", 77)
    m1 = env.match(t["id"], lobos["id"], toros["id"])
    m2 = env.match(t["id"], toros["id"], lobos["id"])

    url = f"{API}/matches/{m1['id']}/stats"
    r = env.client.put(url, json=[{"player_id": outsider["id"], "touchdowns": 1}], headers=env.as_admin)
    assert r.status_code == 422

    r = env.client.put(url, json=[
        {"player_id": rafa["id"], "touchdowns": 3, "tackles": 5},
        {"player_id": marcos["id"], "touchdowns": 1, "interceptions": 2},
    ], headers=env.as_admin)
    assert r.status_code == 200 and len(r.json()) == 2

    # Re-captura del mismo jugador reemplaza (no duplica)
    env.client.put(url, json=[{"player_id": rafa["id"], "touchdowns": 4, "tackles": 5}], headers=env.as_admin)
    env.client.put(f"{API}/matches/{m2['id']}/stats", json=[{"player_id": rafa["id"], "touchdowns": 2}],
                   headers=env.as_admin)

    leaders = env.client.get(f"{API}/tournaments/{t['id']}/player-stats", params={"limit": 2}).json()
    assert leaders[0]["full_name"] == "Rafael Mendoza"
    assert leaders[0]["touchdowns"] == 6 and leaders[0]["games_attended"] == 2 and leaders[0]["tackles"] == 5

    by_int = env.client.get(f"{API}/tournaments/{t['id']}/player-stats", params={"sort_by": "interceptions"}).json()
    assert by_int[0]["full_name"] == "Marcos Rincon"

    detail = env.client.get(f"{API}/players/{rafa['id']}/stats").json()
    assert detail["totals"]["touchdowns"] == 6 and len(detail["matches"]) == 2

    assert env.client.delete(f"{API}/matches/{m1['id']}/stats/{rafa['id']}", headers=env.as_admin).status_code == 204


# ------------------------------------------------------------ usuarios
def test_admin_creates_coach_and_coach_logs_in():
    env = Env()
    r = env.client.post(f"{API}/users", json={"email": "nuevo@liga.mx", "password": "secreto123",
                                              "full_name": "Coach Nuevo"}, headers=env.as_admin)
    assert r.status_code == 201 and r.json()["role"] == "coach"

    login = env.client.post(f"{API}/auth/login", json={"email": "nuevo@liga.mx", "password": "secreto123"})
    assert login.status_code == 200
    me = env.client.get(f"{API}/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["email"] == "nuevo@liga.mx"

    assert env.client.post(f"{API}/auth/login", json={"email": "nuevo@liga.mx", "password": "mal"}).status_code == 401
    r = env.client.patch(f"{API}/users/{env.admin.id}", json={"role": "coach"}, headers=env.as_admin)
    assert r.status_code == 422  # no puedes quitarte tu propio rol


# ------------------------------------------------------------ rol de juegos
def test_generate_round_robin_schedule():
    env = Env()
    t = env.tournament()
    teams = [env.team(t["id"], name) for name in ("TOROS", "LOBOS", "SNAKES", "CHARS", "OLIMPO")]
    url = f"{API}/tournaments/{t['id']}/schedule/generate"

    assert env.client.post(url, json={}, headers=env.as_coach).status_code == 403
    r = env.client.post(url, json={"start_date": "2026-05-18"}, headers=env.as_admin)
    assert r.status_code == 201, r.text
    assert r.json() == {"rounds_created": 5, "matches_created": 10}  # 5 equipos: 5 jornadas, 1 descansa

    rounds = env.client.get(f"{API}/tournaments/{t['id']}/rounds").json()
    assert [r["start_date"] for r in rounds][:2] == ["2026-05-18", "2026-05-25"]
    assert {r["bye_team_id"] for r in rounds} == {team["id"] for team in teams}  # cada equipo descansa una vez

    matches = env.client.get(f"{API}/tournaments/{t['id']}/matches").json()
    assert len({frozenset((m["home_team_id"], m["away_team_id"])) for m in matches}) == 10

    # Regenerar exige confirmacion y se bloquea si ya se jugo algun partido
    assert env.client.post(url, json={}, headers=env.as_admin).status_code == 409
    r = env.client.post(url, json={"replace_existing": True, "double_round": True}, headers=env.as_admin)
    assert r.json() == {"rounds_created": 10, "matches_created": 20}
    first = env.client.get(f"{API}/tournaments/{t['id']}/matches").json()[0]
    env.client.put(f"{API}/matches/{first['id']}/result", json={"home_score": 7, "away_score": 14},
                   headers=env.as_admin)
    assert env.client.post(url, json={"replace_existing": True}, headers=env.as_admin).status_code == 409


# ------------------------------------------------------------ finanzas
def test_finance_is_admin_only_and_computes_balance():
    env = Env()
    t = env.tournament()
    tucanes = env.team(t["id"], "TUCANES", coach_user_id=str(env.coach.id))
    old_star = env.team(t["id"], "OLD STAR")
    base = f"{API}/tournaments/{t['id']}/finance"

    assert env.client.get(f"{base}/summary").status_code == 401
    assert env.client.get(f"{base}/summary", headers=env.as_coach).status_code == 403

    r = env.client.post(f"{base}/registration-fees", json={"amount": 800}, headers=env.as_admin)
    assert r.status_code == 201 and len(r.json()) == 2
    # Repetir no duplica la inscripcion
    assert env.client.post(f"{base}/registration-fees", json={"amount": 800}, headers=env.as_admin).json() == []

    # Como en el Excel: TUCANES inscripcion 800 + multas 1600 - abonos 350 = debe 2050
    for body in (
        {"team_id": tucanes["id"], "type": "fine", "amount": 700, "description": "Pierde por forfeit"},
        {"team_id": tucanes["id"], "type": "fine", "amount": 900, "description": "Cambio de fecha"},
        {"team_id": tucanes["id"], "type": "payment", "amount": 350},
        {"team_id": old_star["id"], "type": "payment", "amount": 800},
    ):
        assert env.client.post(f"{base}/movements", json=body, headers=env.as_admin).status_code == 201

    assert env.client.post(f"{base}/movements", json={"team_id": tucanes["id"], "type": "fine", "amount": -5},
                           headers=env.as_admin).status_code == 422

    summary = env.client.get(f"{base}/summary", headers=env.as_admin).json()
    by_team = {row["team"]["name"]: row for row in summary["teams"]}
    assert float(by_team["TUCANES"]["balance"]) == 2050
    assert float(by_team["TUCANES"]["fines"]) == 1600
    assert float(by_team["OLD STAR"]["balance"]) == 0
    assert float(summary["total_balance"]) == 2050

    fines = env.client.get(f"{base}/movements", params={"type": "fine"}, headers=env.as_admin).json()
    assert len(fines) == 2
    r = env.client.patch(f"{API}/finance/movements/{fines[0]['id']}", json={"amount": 100}, headers=env.as_admin)
    assert r.status_code == 200
    assert env.client.delete(f"{API}/finance/movements/{fines[0]['id']}", headers=env.as_admin).status_code == 204
