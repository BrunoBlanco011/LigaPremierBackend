"""Cedula de referees en Excel, a partir de la plantilla de la liga (templates/cedula_referee.xlsx).

Se edita directamente el XML del .xlsx (solo biblioteca estandar) para conservar el formato
original: bordes, encabezado y pie de impresion, recuadros de PUNTOS y OBSERVACIONES.

La plantilla trae 20 renglones por equipo (filas 6-25). Si un equipo tiene mas jugadores se
insertan renglones antes de los recuadros y la hoja se ajusta a una pagina al imprimir.
"""

import io
import re
import unicodedata
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from app.application.read_models import RefereeSheet, RefereeSheetTeam

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEMPLATE = Path(__file__).parent / "templates" / "cedula_referee.xlsx"
LEAGUE_TZ = ZoneInfo("America/Mexico_City")

SHEET = "xl/worksheets/sheet1.xml"
DRAWING = "xl/drawings/drawing1.xml"
WORKBOOK = "xl/workbook.xml"

FIRST_ROW = 6
TEMPLATE_ROWS = 20  # filas 6-25
LAST_TEMPLATE_ROW = 29  # fin del area de impresion
# Caracteres que caben en un renglon de la columna NOMBRE; si no, el nombre ocupa dos lineas
LONG_NAME = 20
ROW_HEIGHT, TALL_ROW_HEIGHT = 15, 25.5

_MONTHS = ("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
           "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE")
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def render_referee_sheet(sheet: RefereeSheet) -> bytes:
    with zipfile.ZipFile(TEMPLATE) as template:
        infos = template.infolist()
        parts = {info.filename: template.read(info.filename) for info in infos}

    xml = parts[SHEET].decode()
    rows = max(TEMPLATE_ROWS, len(sheet.home.players), len(sheet.away.players))
    extra = rows - TEMPLATE_ROWS
    if extra:
        xml = _insert_rows(xml, extra)
        parts[DRAWING] = _shift_drawing(parts[DRAWING].decode(), extra).encode()
        parts[WORKBOOK] = parts[WORKBOOK].decode().replace(
            f"$P${LAST_TEMPLATE_ROW}", f"$P${LAST_TEMPLATE_ROW + extra}").encode()

    local = sheet.scheduled_at.astimezone(LEAGUE_TZ) if sheet.scheduled_at else None
    if local:
        xml = _set(xml, "C1", f"{local.day:02d} DE {_MONTHS[local.month - 1]} {local.year}")
        xml = _set(xml, "M1", (local.hour * 60 + local.minute) / 1440)  # la celda tiene formato de hora
    if sheet.venue:
        xml = _set(xml, "H1", sheet.venue.upper())
    xml = _set(xml, "C3", sheet.home.name.upper())
    xml = _set(xml, "K3", sheet.away.name.upper())
    xml = _fill_players(xml, sheet.home, "B", "C")
    xml = _fill_players(xml, sheet.away, "J", "K")

    for i in range(rows):
        row = FIRST_ROW + i
        names = [team.players[i].full_name for team in (sheet.home, sheet.away) if i < len(team.players)]
        height = TALL_ROW_HEIGHT if any(len(n) > LONG_NAME for n in names) else ROW_HEIGHT
        xml = xml.replace(f'<row r="{row}" spans="1:16" ht="{ROW_HEIGHT}"', f'<row r="{row}" spans="1:16" ht="{height}"', 1)

    round_label = ""
    if sheet.round:
        round_label = (sheet.round.name or f"Jornada {sheet.round.number}").upper()
    category = f"CATEGORIA {sheet.category}" if sheet.category else sheet.tournament_name
    xml = xml.replace("{{JORNADA}}", _header_text(round_label))
    xml = xml.replace("{{CATEGORIA}}", _header_text(category.upper()))
    parts[SHEET] = xml.encode()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for info in infos:
            out.writestr(info.filename, parts[info.filename])
    return buffer.getvalue()


def referee_sheet_filename(sheet: RefereeSheet) -> str:
    """Nombre ASCII seguro para Content-Disposition: cedula_toros_vs_lobos_2026-10-05.xlsx"""
    parts = ["cedula", _slug(sheet.home.name), "vs", _slug(sheet.away.name)]
    if sheet.scheduled_at:
        parts.append(sheet.scheduled_at.astimezone(LEAGUE_TZ).date().isoformat())
    return "_".join(p for p in parts if p) + ".xlsx"


# ------------------------------------------------------------ celdas
def _fill_players(xml: str, team: RefereeSheetTeam, number_col: str, name_col: str) -> str:
    for i, player in enumerate(team.players):
        row = FIRST_ROW + i
        if player.jersey_number is not None:
            xml = _set(xml, f"{number_col}{row}", player.jersey_number)
        xml = _set(xml, f"{name_col}{row}", player.full_name.upper())
    return xml


def _set(xml: str, ref: str, value: str | int | float) -> str:
    """Escribe en una celda vacia de la plantilla conservando su estilo."""
    if isinstance(value, str):
        content = f' t="inlineStr"><is><t xml:space="preserve">{escape(_INVALID_XML.sub("", value))}</t></is></c>'
    else:
        content = f"><v>{value}</v></c>"
    xml, found = re.subn(rf'<c r="{ref}"( s="\d+")?/>', lambda m: f'<c r="{ref}"{m.group(1) or ""}{content}', xml, count=1)
    if not found:
        raise ValueError(f"La plantilla no tiene la celda vacia {ref}")
    return xml


def _header_text(value: str) -> str:
    # En el encabezado de impresion "&" es un codigo de formato: el literal se escribe "&&"
    return escape(_INVALID_XML.sub("", value).replace("&", "&&"))


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")


# ------------------------------------------------------------ renglones extra
def _insert_rows(xml: str, extra: int) -> str:
    """Duplica el ultimo renglon de jugadores `extra` veces y recorre hacia abajo lo que sigue."""
    last_player_row = FIRST_ROW + TEMPLATE_ROWS - 1

    def renumber(row_xml: str, old: int, new: int) -> str:
        row_xml = row_xml.replace(f'<row r="{old}"', f'<row r="{new}"', 1)
        return re.sub(rf'(<c r="[A-Z]+){old}"', rf'\g<1>{new}"', row_xml)

    full_rows = {int(m.group(1)): m.group(0) for m in re.finditer(r'<row r="(\d+)".*?</row>', xml, re.S)}
    template_row = full_rows[last_player_row]
    rebuilt = []
    for number in sorted(full_rows):
        if number <= last_player_row:
            rebuilt.append(full_rows[number])
            if number == last_player_row:
                rebuilt += [renumber(template_row, number, number + k) for k in range(1, extra + 1)]
        else:
            rebuilt.append(renumber(full_rows[number], number, number + extra))

    xml = re.sub(r"<sheetData>.*</sheetData>", lambda _: "<sheetData>" + "".join(rebuilt) + "</sheetData>", xml, flags=re.S)
    return xml.replace(f'<dimension ref="A1:P{LAST_TEMPLATE_ROW}"/>', f'<dimension ref="A1:P{LAST_TEMPLATE_ROW + extra}"/>')


def _shift_drawing(drawing: str, extra: int) -> str:
    """Baja los recuadros (PUNTOS, OBSERVACIONES) que estan debajo de los jugadores."""
    first_below = FIRST_ROW + TEMPLATE_ROWS - 1  # indice 0-based de la fila 26

    def shift(match: re.Match) -> str:
        row = int(match.group(1))
        return f"<xdr:row>{row + extra if row >= first_below else row}</xdr:row>"

    return re.sub(r"<xdr:row>(\d+)</xdr:row>", shift, drawing)
