import io
import re
import xml.etree.ElementTree as ET
import zipfile

from app.infrastructure.referee_sheet import XLSX_MEDIA_TYPE
from tests.helpers import Env

API = "/api/v1"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _cells(book: zipfile.ZipFile) -> dict[str, str]:
    sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    shared = [si.findtext(f"{NS}t") for si in ET.fromstring(book.read("xl/sharedStrings.xml"))]
    cells = {}
    for c in sheet.iter(f"{NS}c"):
        if c.get("t") == "inlineStr":
            cells[c.get("r")] = c.find(f"{NS}is").findtext(f"{NS}t")
        elif c.get("t") == "s":
            cells[c.get("r")] = shared[int(c.findtext(f"{NS}v"))]
        elif c.find(f"{NS}v") is not None:
            cells[c.get("r")] = c.findtext(f"{NS}v")
    return cells


def _setup(env: Env, home_players: list[tuple[int | None, str]], away_players: list[tuple[int | None, str]]):
    t = env.tournament(category="Mixto Silver")
    home = env.team(t["id"], "TOROS")
    away = env.team(t["id"], "Lobos & Cía")
    for team, players in ((home, home_players), (away, away_players)):
        for number, name in players:
            r = env.client.post(f"{API}/clubs/{team['club_id']}/players",
                                json={"full_name": name, "jersey_number": number}, headers=env.as_admin)
            assert r.status_code == 201, r.text
    round_ = env.client.post(f"{API}/tournaments/{t['id']}/rounds", json={"number": 3}, headers=env.as_admin).json()
    # 03:00 UTC = 21:00 del dia anterior en Chiapas
    return env.match(t["id"], home["id"], away["id"], round_id=round_["id"],
                     scheduled_at="2026-10-06T03:00:00Z", venue="Parque Caña Hueca")


def test_referee_sheet_has_match_data_and_rosters():
    env = Env()
    match = _setup(
        env,
        home_players=[(17, "Marcos Rincon"), (4, "Lucia Guadalupe Perez Jimenez"), (None, "Sin Numero")],
        away_players=[(9, "Kira de Paz")],
    )
    # Las bajas no aparecen
    club_players = env.client.get(f"{API}/teams/{match['home_team_id']}/players", headers=env.as_admin).json()
    baja = next(p for p in club_players if p["full_name"] == "Sin Numero")
    env.client.patch(f"{API}/players/{baja['id']}", json={"is_active": False}, headers=env.as_admin)

    r = env.client.get(f"{API}/matches/{match['id']}/referee-sheet", headers=env.as_admin)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == XLSX_MEDIA_TYPE
    assert r.headers["content-disposition"] == 'attachment; filename="cedula_toros_vs_lobos_cia_2026-10-05.xlsx"'

    book = zipfile.ZipFile(io.BytesIO(r.content))
    for name in book.namelist():  # todo el XML debe seguir siendo valido
        if name.endswith((".xml", ".rels")):
            ET.fromstring(book.read(name))
    cells = _cells(book)
    assert cells["C1"] == "05 DE OCTUBRE 2026"
    assert cells["H1"] == "PARQUE CAÑA HUECA"
    assert float(cells["M1"]) == 0.875  # 21:00
    assert cells["C3"] == "TOROS" and cells["K3"] == "LOBOS & CÍA"
    # Ordenados por numero
    assert (cells["B6"], cells["C6"]) == ("4", "LUCIA GUADALUPE PEREZ JIMENEZ")
    assert (cells["B7"], cells["C7"]) == ("17", "MARCOS RINCON")
    assert "C8" not in cells
    assert (cells["J6"], cells["K6"]) == ("9", "KIRA DE PAZ")
    # Las columnas de desempeno quedan vacias para el referee
    assert not any(ref in cells for ref in ("D6", "H6", "L6", "P6"))
    assert cells["H5"] == "TACLES" and cells["B1"] == "FECHA"

    sheet = book.read("xl/worksheets/sheet1.xml").decode()
    assert "JORNADA 3" in sheet and "CATEGORIA MIXTO SILVER" in sheet and "{{" not in sheet
    assert '<row r="6" spans="1:16" ht="25.5"' in sheet  # nombre largo: dos lineas
    assert '<row r="7" spans="1:16" ht="15"' in sheet


def test_referee_sheet_grows_for_big_rosters():
    env = Env()
    match = _setup(env, home_players=[(n, f"Jugador {n}") for n in range(23)], away_players=[])
    book = zipfile.ZipFile(io.BytesIO(
        env.client.get(f"{API}/matches/{match['id']}/referee-sheet", headers=env.as_admin).content))
    cells = _cells(book)
    assert cells["C28"] == "JUGADOR 22"  # 23 jugadores: filas 6-28

    sheet = book.read("xl/worksheets/sheet1.xml").decode()
    assert '<dimension ref="A1:P32"/>' in sheet
    assert re.findall(r'<row r="(\d+)"', sheet) == [str(n) for n in range(1, 33)]
    assert "$P$32" in book.read("xl/workbook.xml").decode()
    # Los recuadros de PUNTOS y OBSERVACIONES bajan 3 filas
    assert "<xdr:row>28</xdr:row>" in book.read("xl/drawings/drawing1.xml").decode()


def test_referee_sheet_is_admin_only():
    env = Env()
    match = _setup(env, home_players=[], away_players=[])
    url = f"{API}/matches/{match['id']}/referee-sheet"
    assert env.client.get(url).status_code == 401
    assert env.client.get(url, headers=env.as_coach).status_code == 403
    assert env.client.get(f"{API}/matches/00000000-0000-0000-0000-000000000000/referee-sheet",
                          headers=env.as_admin).status_code == 404
