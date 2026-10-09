from tests.helpers import Env

API = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # firma real de PNG: el servidor verifica el contenido


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
    t = env.tournament(category="Mixta")
    assert (t["points_win"], t["points_loss"], t["end_date"]) == (2, 0, None)
    r = env.client.patch(f"{API}/tournaments/{t['id']}", json={"status": "active"}, headers=env.as_admin)
    assert r.status_code == 200 and r.json()["status"] == "active"
    for field in ({"season": "2026"}, {"end_date": "2026-05-01"}, {"points_win": 3}):  # ya no se capturan
        r = env.client.patch(f"{API}/tournaments/{t['id']}", json=field, headers=env.as_admin)
        assert r.status_code == 422, field
    assert env.client.delete(f"{API}/tournaments/{t['id']}", headers=env.as_admin).status_code == 204
    assert env.client.get(f"{API}/tournaments/{t['id']}").status_code == 404


# ------------------------------------------------------------ clubes e inscripciones
def test_club_crud_unique_name_and_coach_assignment():
    env = Env()
    env.club("TOROS", coach_name="Rafa")
    assert env.client.post(f"{API}/clubs", json={"name": "toros"}, headers=env.as_admin).status_code == 409
    assert env.client.post(f"{API}/clubs", json={"name": "X"}, headers=env.as_coach).status_code == 403

    r = env.client.post(f"{API}/clubs", json={"name": "LOBOS", "coach_user_id": str(env.admin.id)},
                        headers=env.as_admin)
    assert r.status_code == 422  # el usuario asignado debe ser coach

    lobos = env.club("LOBOS", coach_user_id=str(env.coach.id))
    mine = env.client.get(f"{API}/me/clubs", headers=env.as_coach).json()
    assert [x["id"] for x in mine] == [lobos["id"]]

    r = env.client.patch(f"{API}/clubs/{lobos['id']}", json={"name": "LOBOS PLATEADOS"}, headers=env.as_admin)
    assert r.status_code == 200 and r.json()["name"] == "LOBOS PLATEADOS"
    assert env.client.delete(f"{API}/clubs/{lobos['id']}", headers=env.as_admin).status_code == 204


def test_register_clubs_to_tournaments():
    env = Env()
    t1, t2 = env.tournament(name="Apertura"), env.tournament(name="Clausura")
    toros, lobos = env.club("TOROS"), env.club("LOBOS")
    url = f"{API}/tournaments/{t1['id']}/teams"

    r = env.client.post(url, json={"club_ids": [toros["id"], lobos["id"]]}, headers=env.as_admin)
    assert r.status_code == 201, r.text
    teams = r.json()
    assert {t["name"] for t in teams} == {"TOROS", "LOBOS"}  # nombre tomado del club
    assert env.client.post(url, json={"club_ids": [toros["id"]]}, headers=env.as_admin).status_code == 409

    # El mismo club juega otro torneo: nueva inscripcion, mismo club
    t2_team = env.client.post(f"{API}/tournaments/{t2['id']}/teams", json={"club_ids": [toros["id"]]},
                              headers=env.as_admin).json()[0]
    assert t2_team["club_id"] == toros["id"] and t2_team["id"] != teams[0]["id"]

    # Un club con torneos jugados no se puede borrar (se conserva el historial)
    assert env.client.delete(f"{API}/clubs/{toros['id']}", headers=env.as_admin).status_code == 409

    # Cambiar el logo del club se refleja en todas sus inscripciones
    files = {"file": ("logo.png", PNG, "image/png")}
    r = env.client.post(f"{API}/clubs/{toros['id']}/logo", files=files, headers=env.as_admin)
    assert r.status_code == 200 and r.json()["logo_url"].startswith("https://cdn.test/")
    assert env.client.get(f"{API}/teams/{t2_team['id']}").json()["logo_url"] == r.json()["logo_url"]
    bad = {"file": ("logo.gif", b"GIF", "image/gif")}
    assert env.client.post(f"{API}/clubs/{toros['id']}/logo", files=bad, headers=env.as_admin).status_code == 422

    # Baja de inscripcion
    assert env.client.delete(f"{API}/teams/{t2_team['id']}", headers=env.as_admin).status_code == 204


def test_club_history():
    env = Env()
    t1 = env.tournament(name="Apertura", start_date="2026-01-10")
    t2 = env.tournament(name="Clausura", start_date="2026-06-10")
    for t in (t1, t2):
        toros, lobos = env.team(t["id"], "TOROS"), env.team(t["id"], "LOBOS")
        m = env.match(t["id"], toros["id"], lobos["id"])
        score = {"home_score": 30, "away_score": 12} if t is t1 else {"home_score": 6, "away_score": 21}
        env.client.put(f"{API}/matches/{m['id']}/result", json=score, headers=env.as_admin)

    history = env.client.get(f"{API}/clubs/{toros['club_id']}/history").json()
    assert [h["tournament"]["name"] for h in history] == ["Clausura", "Apertura"]
    assert [h["standing"]["position"] for h in history] == [2, 1]
    assert history[0]["teams_count"] == 2


# ------------------------------------------------------------ jugadores / coach
def test_player_birth_date_is_optional_and_private():
    env = Env()
    club = env.club("TOROS JR", coach_user_id=str(env.coach.id))
    url = f"{API}/clubs/{club['id']}/players"

    r = env.client.post(url, json={"full_name": "Diego Ruiz", "jersey_number": 9, "birth_date": "2012-05-14"},
                        headers=env.as_coach)
    assert r.status_code == 201 and r.json()["birth_date"] == "2012-05-14"
    player = r.json()
    assert env.client.post(url, json={"full_name": "Sin fecha"}, headers=env.as_coach).json()["birth_date"] is None

    # Fechas imposibles
    for bad in ("2999-01-01", "1850-01-01", "no-es-fecha"):
        r = env.client.post(url, json={"full_name": "X", "birth_date": bad}, headers=env.as_coach)
        assert r.status_code == 422, bad

    # Admin y coach del club la ven; el publico no
    assert env.client.get(f"{API}/players/{player['id']}", headers=env.as_admin).json()["birth_date"] == "2012-05-14"
    assert env.client.get(f"{API}/players/{player['id']}", headers=env.as_coach).json()["birth_date"] == "2012-05-14"
    assert env.client.get(f"{API}/players/{player['id']}").json()["birth_date"] is None
    assert all(p["birth_date"] is None for p in env.client.get(url).json())
    assert any(p["birth_date"] for p in env.client.get(url, headers=env.as_coach).json())

    # Se puede corregir y borrar
    pid = player["id"]
    r = env.client.patch(f"{API}/players/{pid}", json={"birth_date": "2012-06-01"}, headers=env.as_coach)
    assert r.json()["birth_date"] == "2012-06-01"
    r = env.client.patch(f"{API}/players/{pid}", json={"birth_date": None}, headers=env.as_coach)
    assert r.json()["birth_date"] is None


def test_coach_manages_only_own_club_players():
    env = Env()
    mine = env.club("LOBOS", coach_user_id=str(env.coach.id))
    other = env.club("TOROS")

    r = env.client.post(f"{API}/clubs/{mine['id']}/players", json={"full_name": "Marcos Rincon", "jersey_number": 17},
                        headers=env.as_coach)
    assert r.status_code == 201, r.text
    player = r.json()

    dup = env.client.post(f"{API}/clubs/{mine['id']}/players", json={"full_name": "Otro", "jersey_number": 17},
                          headers=env.as_coach)
    assert dup.status_code == 409

    forbidden = env.client.post(f"{API}/clubs/{other['id']}/players", json={"full_name": "X"}, headers=env.as_coach)
    assert forbidden.status_code == 403

    r = env.client.patch(f"{API}/players/{player['id']}", json={"jersey_number": 7}, headers=env.as_coach)
    assert r.status_code == 200 and r.json()["jersey_number"] == 7

    # El coach no puede transferir jugadores; el admin si
    move = {"club_id": other["id"]}
    assert env.client.patch(f"{API}/players/{player['id']}", json=move, headers=env.as_coach).status_code == 403

    # Una baja deja de verse en la plantilla publica, pero el coach la sigue viendo
    env.client.patch(f"{API}/players/{player['id']}", json={"is_active": False}, headers=env.as_coach)
    assert env.client.get(f"{API}/clubs/{mine['id']}/players").json() == []
    assert len(env.client.get(f"{API}/clubs/{mine['id']}/players", headers=env.as_coach).json()) == 1

    # Nombre, numero y fecha de nacimiento (opcional): otros campos se rechazan
    extra = env.client.post(f"{API}/clubs/{mine['id']}/players", json={"full_name": "X", "position": "QB"},
                            headers=env.as_coach)
    assert extra.status_code == 422

    r = env.client.patch(f"{API}/players/{player['id']}", json=move, headers=env.as_admin)
    assert r.status_code == 200 and r.json()["club_id"] == other["id"]
    assert env.client.delete(f"{API}/players/{player['id']}", headers=env.as_admin).status_code == 204


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
        r = env.client.post(f"{API}/clubs/{team['club_id']}/players", json={"full_name": name, "jersey_number": n},
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
    assert [s["tournament_name"] for s in detail["by_tournament"]] == ["Apertura 2026"]
    assert detail["by_tournament"][0]["totals"]["touchdowns"] == 6

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
    tournament = env.client.get(f"{API}/tournaments/{t['id']}").json()
    assert (tournament["start_date"], tournament["end_date"]) == ("2026-05-18", "2026-06-15")  # lo marca el rol

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


def test_schedule_with_weekdays_kickoff_times_and_venue():
    from datetime import datetime, timezone

    env = Env()
    t = env.tournament()
    for name in ("TOROS", "LOBOS", "SNAKES", "CHARS"):
        env.team(t["id"], name)
    url = f"{API}/tournaments/{t['id']}/schedule/generate"

    r = env.client.post(url, json={"weekdays": [6]}, headers=env.as_admin)
    assert r.status_code == 422  # sin fecha de inicio no se pueden programar dias

    body = {"start_date": "2026-05-18", "weekdays": [5, 6], "start_time": "09:00",
            "match_duration_minutes": 60, "venue": "Campo Norte"}
    r = env.client.post(url, json=body, headers=env.as_admin)
    assert r.status_code == 201, r.text

    rounds = env.client.get(f"{API}/tournaments/{t['id']}/rounds").json()
    assert [x["start_date"] for x in rounds] == ["2026-05-23", "2026-05-24", "2026-05-30"]  # sab, dom, sab

    matches = env.client.get(f"{API}/tournaments/{t['id']}/matches").json()
    first_round = [m for m in matches if m["round_id"] == rounds[0]["id"]]
    kickoffs = sorted(datetime.fromisoformat(m["scheduled_at"]).astimezone(timezone.utc) for m in first_round)
    # 9:00 y 10:00 hora de Ciudad de Mexico (UTC-6), uno tras otro
    assert kickoffs == [datetime(2026, 5, 23, 15, tzinfo=timezone.utc), datetime(2026, 5, 23, 16, tzinfo=timezone.utc)]
    assert {m["venue"] for m in matches} == {"Campo Norte"}


def test_schedule_max_matches_per_day_spreads_the_round():
    from datetime import datetime, timezone

    env = Env()
    t = env.tournament()
    for name in ("TOROS", "LOBOS", "SNAKES", "CHARS"):
        env.team(t["id"], name)
    body = {"start_date": "2026-05-18", "weekdays": [5, 6], "start_time": "10:00", "max_matches_per_day": 1}
    r = env.client.post(f"{API}/tournaments/{t['id']}/schedule/generate", json=body, headers=env.as_admin)
    assert r.status_code == 201, r.text

    rounds = env.client.get(f"{API}/tournaments/{t['id']}/rounds").json()
    # 2 partidos por jornada, 1 por dia: cada jornada es un fin de semana (sabado y domingo)
    assert [(x["start_date"], x["end_date"]) for x in rounds] == [
        ("2026-05-23", "2026-05-24"), ("2026-05-30", "2026-05-31"), ("2026-06-06", "2026-06-07")]
    matches = env.client.get(f"{API}/tournaments/{t['id']}/matches").json()
    first = sorted(datetime.fromisoformat(m["scheduled_at"]).astimezone(timezone.utc)
                   for m in matches if m["round_id"] == rounds[0]["id"])
    assert [(d.day, d.hour) for d in first] == [(23, 16), (24, 16)]  # 10:00 en CDMX = 16:00 UTC
    tournament = env.client.get(f"{API}/tournaments/{t['id']}").json()
    assert tournament["end_date"] == "2026-06-07"
