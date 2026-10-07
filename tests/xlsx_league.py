"""Lee la temporada real del archivo "ROL DE JUEGOS (1).xlsx" (raiz del repo) para las
pruebas de volumen. El archivo trae nombres reales de jugadores, por eso no se versiona
(.gitignore) y las pruebas que lo usan se omiten si no esta.

Solo usa la libreria estandar (un .xlsx es un zip con XML).

- Hoja1: tabla de posiciones capturada a mano (A5:I18), resultados por jornada
  en bloques "LOCAL pts | VS | VISITANTE pts" y el resumen de adeudos (AE18:AI30).
- Hoja2: plantillas por equipo con totales de la temporada por jugador.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

XLSX_PATH = Path(__file__).resolve().parent.parent / "ROL DE JUEGOS (1).xlsx"

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_T = "{%s}t" % _NS["m"]

# Nombres cortos o con errores de dedo que aparecen en la hoja
_ALIASES = {"LOBOS": "LOBOS PLATEADOS", "TUNE": "TUNE SQUAD", "TUNES": "TUNE SQUAD"}


@dataclass
class SheetPlayer:
    full_name: str
    jersey_number: int | None
    games_attended: int
    touchdowns: int
    td_passes: int
    interceptions: int
    sacks: int
    tackles: int


@dataclass
class SheetMatch:
    round_number: int | None  # None = partido pendiente que se reprogramo
    home: str
    away: str
    status: str  # finished | forfeit | cancelled | scheduled
    home_score: int | None = None
    away_score: int | None = None
    forfeit_loser: str | None = None


@dataclass
class SheetStanding:
    team: str
    position: int
    played: int
    won: int
    lost: int
    points_for: int
    points_against: int
    points: int


@dataclass
class SheetBalance:
    team: str
    registration_due: int  # 0 = inscripcion pagada ("X")
    fines: int
    payments: int
    balance: int


@dataclass
class League:
    teams: list[str]
    rosters: dict[str, list[SheetPlayer]]
    matches: list[SheetMatch]
    standings: list[SheetStanding]
    balances: list[SheetBalance] = field(default_factory=list)


def available() -> bool:
    return XLSX_PATH.exists()


# ---------------------------------------------------------------- lectura cruda
def _read_sheets(path: Path) -> dict[str, dict[str, str]]:
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(_T)))
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    sheets = {}
    for sheet in workbook.find("m:sheets", _NS):
        target = rels[sheet.get("{%s}id" % _NS["r"])].lstrip("/")
        root = ET.fromstring(z.read(target if target.startswith("xl/") else f"xl/{target}"))
        cells = {}
        for c in root.iter("{%s}c" % _NS["m"]):
            v = c.find("m:v", _NS)
            if v is not None:
                cells[c.get("r")] = shared[int(v.text)] if c.get("t") == "s" else v.text
            elif (inline := c.find("m:is", _NS)) is not None:
                cells[c.get("r")] = "".join(t.text or "" for t in inline.iter(_T))
        sheets[sheet.get("name")] = cells
    return sheets


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def _col_name(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def _norm(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip().upper()
    return _ALIASES.get(name, name)


def _int(value: str | None) -> int:
    return int(float(value)) if value not in (None, "") else 0


# ---------------------------------------------------------------- Hoja1
_TEAM_SCORE = re.compile(r"^(.*?)\s*(\d+)?\s*$")


def _team_and_score(text: str) -> tuple[str, int | None]:
    m = _TEAM_SCORE.match(text.strip())
    return _norm(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def _parse_standings(cells: dict[str, str]) -> list[SheetStanding]:
    rows = []
    for r in range(6, 20):
        if not cells.get(f"B{r}") or not cells.get(f"A{r}", "").strip().isdigit():
            continue
        rows.append(SheetStanding(
            team=_norm(cells[f"B{r}"]), position=_int(cells[f"A{r}"]), played=_int(cells[f"C{r}"]),
            won=_int(cells[f"D{r}"]), lost=_int(cells[f"E{r}"]), points_for=_int(cells[f"F{r}"]),
            points_against=_int(cells[f"G{r}"]), points=_int(cells[f"I{r}"]),
        ))
    return sorted(rows, key=lambda s: s.position)


def _parse_matches(cells: dict[str, str], teams: set[str]) -> list[SheetMatch]:
    """Bloques de 3 columnas (local | VS | visitante) que empiezan en K, P, U, Z y AE."""
    matches = []
    for start in ("K", "P", "U", "Z", "AE"):
        c0 = _col_index(start)
        home_col, mid_col, away_col = _col_name(c0), _col_name(c0 + 1), _col_name(c0 + 2)
        round_number: int | None = None
        for r in range(3, 32):
            mid = (cells.get(f"{mid_col}{r}") or "").strip().upper()
            # Encabezado de bloque: "JORNADA n" o "PENDIENTES"
            if header := re.match(r"JORNADA (\d+)", mid):
                round_number = int(header.group(1))
                continue
            if mid == "PENDIENTES":
                round_number = None
                continue
            home_raw, away_raw = cells.get(f"{home_col}{r}"), cells.get(f"{away_col}{r}")
            if not home_raw or not away_raw:
                continue
            home, home_score = _team_and_score(re.sub(r"(?i)\bdebe\b.*", "", home_raw))
            away, away_score = _team_and_score(away_raw)
            if home not in teams or away not in teams:
                continue  # notas de adeudos u otras anotaciones
            if mid == "VS" and home_score is not None and away_score is not None:
                # En la hoja los forfeits se anotan 21-0 (o 0-21)
                if {home_score, away_score} == {0, 21}:
                    loser = home if home_score == 0 else away
                    matches.append(SheetMatch(round_number, home, away, "forfeit", forfeit_loser=loser))
                else:
                    matches.append(SheetMatch(round_number, home, away, "finished", home_score, away_score))
            elif "FORFIT" in mid or "FORFEIT" in mid or "FORFIET" in mid:
                matches.append(SheetMatch(round_number, home, away, "forfeit", forfeit_loser=home))
            elif "CANCEL" in mid:
                matches.append(SheetMatch(round_number, home, away, "cancelled"))
            elif mid == "BYE" or "DEBE" in mid:
                continue  # notas: el partido se reprogramo y aparece en PENDIENTES
            else:
                matches.append(SheetMatch(round_number, home, away, "scheduled"))
    return matches


def _parse_balances(cells: dict[str, str], teams: set[str]) -> list[SheetBalance]:
    balances = []
    for r in range(19, 31):
        team = _norm(cells.get(f"AE{r}") or "")
        if team not in teams:
            continue
        registration = cells.get(f"AF{r}", "").strip().upper()
        due = 0 if registration == "X" else _int(registration)
        fines, payments = _int(cells.get(f"AG{r}")), _int(cells.get(f"AH{r}"))
        balance = _int(cells.get(f"AI{r}")) if cells.get(f"AI{r}") else due + fines - payments
        balances.append(SheetBalance(team, due, fines, payments, balance))
    return balances


# ---------------------------------------------------------------- Hoja2
_PLAYER = re.compile(r"^(.*?)\s*#\s*(\d+)")


def _parse_rosters(cells: dict[str, str], teams: set[str]) -> dict[str, list[SheetPlayer]]:
    rosters: dict[str, list[SheetPlayer]] = {}
    current: str | None = None
    last_row = max(int(re.sub(r"\D", "", ref)) for ref in cells)
    for r in range(2, last_row + 1):
        b = (cells.get(f"B{r}") or "").strip()
        if not b:
            continue
        if _norm(b) in teams and not cells.get(f"A{r}"):
            current = _norm(b)
            rosters[current] = []
            continue
        a = (cells.get(f"A{r}") or "").strip()
        if current is None or a.upper().startswith("ASISTENTE") or cells.get(f"G{r}") == "VS":
            continue
        if m := _PLAYER.match(b):
            name, jersey = m.group(1).strip(), int(m.group(2))
        else:
            name, jersey = b, None
        rosters[current].append(SheetPlayer(
            full_name=name, jersey_number=jersey, games_attended=_int(a),
            touchdowns=_int(cells.get(f"C{r}")), td_passes=_int(cells.get(f"D{r}")),
            interceptions=_int(cells.get(f"E{r}")), sacks=_int(cells.get(f"F{r}")),
            tackles=_int(cells.get(f"G{r}")),
        ))
    return rosters


def load(path: Path = XLSX_PATH) -> League:
    sheets = _read_sheets(path)
    hoja1, hoja2 = sheets["Hoja1"], sheets["Hoja2"]
    standings = _parse_standings(hoja1)
    teams = {s.team for s in standings}
    return League(
        teams=[s.team for s in standings],
        rosters=_parse_rosters(hoja2, teams),
        matches=_parse_matches(hoja1, teams),
        standings=standings,
        balances=_parse_balances(hoja1, teams),
    )


# ---------------------------------------------------------------- datos limpios
def clean(league: League) -> tuple[League, list[str]]:
    """Corrige o simula lo que la hoja trae inconsistente y devuelve que se cambio:

    - Dorsal repetido dentro del club: se asigna el siguiente numero libre.
    - Asistencia mayor a los partidos jugados por el equipo: se limita.
    - Tabla de posiciones: se recalcula con los resultados partido por partido
      (la capturada a mano no cuadra: JJ impar, puntos a favor != en contra).
    """
    fixes: list[str] = []
    decided = [m for m in league.matches if m.status in ("finished", "forfeit")]
    games = {team: sum(team in (m.home, m.away) for m in decided) for team in league.teams}

    rosters = {}
    for team, roster in league.rosters.items():
        used = {p.jersey_number for p in roster if p.jersey_number is not None}
        seen: set[int] = set()
        cleaned = []
        for p in roster:
            jersey, attended = p.jersey_number, p.games_attended
            if jersey is not None and jersey in seen:
                new = next(n for n in range(1, 1000) if n not in used)
                used.add(new)
                fixes.append(f"{team}: dorsal #{jersey} repetido -> #{new}")
                jersey = new
            if jersey is not None:
                seen.add(jersey)
            if attended > games[team]:
                fixes.append(f"{team}: asistencia {attended} > {games[team]} partidos -> {games[team]}")
                attended = games[team]
            cleaned.append(SheetPlayer(**{**p.__dict__, "jersey_number": jersey, "games_attended": attended}))
        rosters[team] = cleaned

    standings = expected_standings(league.teams, league.matches)
    sheet = {s.team: s for s in league.standings}
    for row in standings:
        old = sheet[row.team]
        diff = [f"{k} {getattr(old, k)}->{getattr(row, k)}"
                for k in ("position", "played", "won", "lost", "points_for", "points_against", "points")
                if getattr(old, k) != getattr(row, k)]
        if diff:
            fixes.append(f"tabla {row.team}: " + ", ".join(diff))
    return League(league.teams, rosters, league.matches, standings, league.balances), fixes


def expected_standings(teams: list[str], matches: list[SheetMatch]) -> list[SheetStanding]:
    """Tabla calculada a mano, independiente del codigo de la app: 2 puntos por victoria,
    forfeit 21-0 y desempate puntos -> a favor -> diferencia -> menos en contra -> nombre."""
    rows = {t: SheetStanding(t, 0, 0, 0, 0, 0, 0, 0) for t in teams}
    for m in matches:
        if m.status == "forfeit":
            loser = m.forfeit_loser
            winner = m.away if loser == m.home else m.home
            scores = {winner: 21, loser: 0}
        elif m.status == "finished":
            scores = {m.home: m.home_score, m.away: m.away_score}
            winner = max(scores, key=scores.get)
        else:
            continue
        for team, rival in ((m.home, m.away), (m.away, m.home)):
            row = rows[team]
            row.played += 1
            row.points_for += scores[team]
            row.points_against += scores[rival]
            if team == winner:
                row.won += 1
                row.points += 2
            else:
                row.lost += 1
    ordered = sorted(rows.values(), key=lambda r: (
        -r.points, -r.points_for, -(r.points_for - r.points_against), r.points_against, r.team))
    for i, row in enumerate(ordered, 1):
        row.position = i
    return ordered
