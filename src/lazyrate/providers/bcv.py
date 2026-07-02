"""Proveedor BCV: tasas oficiales desde el Excel trimestral "otras monedas".

El BCV publica un .xls por trimestre con una hoja por día hábil (nombradas
DDMMYYYY, la más reciente primero). De cada hoja se toma la "Fecha Valor" y la
columna "Bs./M.E. Venta (ASK)" (Bs por 1 unidad de la divisa) para todas las
monedas de ``BCV_CURRENCIES``.

Nota sobre SSL (fallback acotado): la descarga usa primero ``urlopen`` con el
contexto por defecto (certificado verificado). SOLO si falla la verificación
del certificado (``ssl.SSLCertVerificationError`` directo o como ``reason`` de
``URLError``) se reintenta UNA vez con un contexto sin verificación creado
localmente y pasado solo a ese ``urlopen``; cualquier otro ``SSLError`` (EOF,
handshake) se propaga. La cadena del BCV falla en sistemas sin su CA
intermedia (verificado en vivo: ``CERTIFICATE_VERIFY_FAILED: unable to get
local issuer certificate``); la URL la construye este módulo (nunca viene de
configuración), así que el downgrade queda acotado al host del BCV.
"""

from __future__ import annotations

import logging
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import xlrd

from lazyrate.config import BCV_CURRENCIES, cache_dir
from lazyrate.providers.base import HTTP_TIMEOUT, MAX_RESPONSE_BYTES, Quote, now_utc, today_caracas

if TYPE_CHECKING:
    from lazyrate.config import Config

log = logging.getLogger(__name__)

BASE_URL = "https://www.bcv.org.ve/sites/default/files/EstadisticasGeneral"
QUARTER_LETTERS = "abcd"
QUARTER_START_MONTHS = (1, 4, 7, 10)
CACHE_MAX_AGE_SECONDS = 6 * 3600

# Layout verificado contra los archivos reales del BCV (2026)
_VALUE_DATE_CELL = (4, 3)  # "Fecha Valor:  DD/MM/YYYY"
_DATA_START_ROW = 10  # cabecera en fila 8, datos desde la 10
_CURRENCY_COL = 1  # código ISO de la moneda (PTR, EUR, USD, ...)
_ASK_COL = 6  # "Bs./M.E. Venta (ASK)" = Bs por 1 unidad

_VALUE_DATE_RE = re.compile(r"Fecha Valor\s*:\s*(\d{2}/\d{2}/\d{4})")


def quarter_letter(month: int) -> str:
    """Letra del trimestre en el nombre del archivo: ene-mar→a ... oct-dic→d."""
    return QUARTER_LETTERS[(month - 1) // 3]


def quarter_filename(year: int, month: int) -> str:
    return f"2_1_2{quarter_letter(month)}{year % 100:02d}_otrasmonedas.xls"


def quarter_url(year: int, month: int) -> str:
    return f"{BASE_URL}/{quarter_filename(year, month)}"


def previous_quarter(year: int, month: int) -> tuple[int, int]:
    """(año, mes) del trimestre anterior; enero→diciembre del año pasado."""
    first_month = QUARTER_START_MONTHS[(month - 1) // 3]
    if first_month == 1:
        return year - 1, 12
    return year, first_month - 1


# Magic bytes OLE2 de un .xls; una página HTML (mantenimiento, WAF) no los tiene
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"


def _read_limited(response, url: str) -> bytes:
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Respuesta de más de {MAX_RESPONSE_BYTES} bytes; descartada")
    if not data.startswith(_XLS_MAGIC):
        raise ValueError(f"La respuesta de {url} no es un .xls (¿página de mantenimiento?)")
    return data


def download(url: str) -> bytes:
    """Descarga verificada; fallback sin verificar SOLO ante fallo de certificado."""
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
            return _read_limited(response, url)
    except ssl.SSLCertVerificationError:
        pass
    except urllib.error.URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise
    log.warning("Fallo de certificado con %s; reintentando sin verificación SSL", url)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT, context=context) as response:
        return _read_limited(response, url)


def fetch_workbook(year: int, month: int) -> Path:
    """Devuelve la ruta local del .xls del trimestre, usando caché de 6 horas.

    Si la descarga falla y existe una caché (aunque vieja), se usa con warning.
    """
    path = cache_dir() / quarter_filename(year, month)
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_MAX_AGE_SECONDS:
        return path
    url = quarter_url(year, month)
    try:
        data = download(url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if path.exists():
            log.warning("No se pudo descargar %s (%s); usando caché vieja %s", url, exc, path)
            return path
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def _sheet_value_date(sheet) -> date | None:
    row, col = _VALUE_DATE_CELL
    if sheet.nrows <= row or sheet.ncols <= col:
        return None
    match = _VALUE_DATE_RE.search(str(sheet.cell_value(row, col)))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_sheet(sheet, fetched_at: datetime) -> list[Quote]:
    """Cotizaciones de una hoja diaria; ignora filas no convertibles (p.ej. '----')."""
    value_date = _sheet_value_date(sheet)
    if value_date is None:
        log.warning("Hoja BCV %s sin 'Fecha Valor' reconocible; ignorada", sheet.name)
        return []
    if sheet.ncols <= _ASK_COL:
        log.warning("Hoja BCV %s sin columna ASK; ignorada", sheet.name)
        return []
    quotes: list[Quote] = []
    for row in range(_DATA_START_ROW, sheet.nrows):
        currency = str(sheet.cell_value(row, _CURRENCY_COL)).strip()
        if currency not in BCV_CURRENCIES:
            continue
        try:
            rate = float(sheet.cell_value(row, _ASK_COL))
        except (TypeError, ValueError):
            log.debug("Celda no numérica en %s fila %d (%s); ignorada", sheet.name, row, currency)
            continue
        quotes.append(
            Quote(
                source="bcv",
                currency=currency,
                rate=round(rate, 4),
                fetched_at=fetched_at,
                value_date=value_date,
                meta={"sheet": sheet.name},
            )
        )
    return quotes


def parse_workbook(path: Path) -> list[Quote]:
    """Parsea TODAS las hojas del .xls trimestral (una por día hábil)."""
    try:
        workbook = xlrd.open_workbook(str(path))
    except xlrd.XLRDError as exc:
        # Caché corrupta (p.ej. HTML cacheado): descartarla para forzar re-descarga
        path.unlink(missing_ok=True)
        raise ValueError(f"Excel del BCV ilegible ({path.name}); caché descartada") from exc
    fetched_at = now_utc()
    quotes: list[Quote] = []
    for sheet in workbook.sheets():
        quotes.extend(_parse_sheet(sheet, fetched_at))
    return quotes


def _quarter_quotes(year: int, month: int) -> list[Quote]:
    return parse_workbook(fetch_workbook(year, month))


class BcvProvider:
    """Descarga el trimestre actual; si aún no cubre hoy, añade el anterior."""

    name = "bcv"

    def fetch(self, cfg: Config) -> list[Quote]:
        today = today_caracas()
        quotes: list[Quote] = []
        try:
            quotes = _quarter_quotes(today.year, today.month)
        except urllib.error.HTTPError as exc:
            # Los primeros días del trimestre el archivo puede no existir aún
            if exc.code != 404:
                raise
            log.warning("Excel del trimestre actual aún no publicado (404): %s", exc.url)
        except ValueError as exc:
            log.warning("Excel del trimestre actual ilegible: %s", exc)
        if not quotes or min(q.value_date for q in quotes) > today:
            # Trimestre recién empezado: solo trae la fecha valor de mañana (o 404)
            prev_year, prev_month = previous_quarter(today.year, today.month)
            try:
                quotes.extend(_quarter_quotes(prev_year, prev_month))
            except (urllib.error.URLError, OSError, ValueError) as exc:
                log.warning("No se pudo obtener el trimestre anterior del BCV: %s", exc)
        return quotes


def backfill(cfg: Config, year: int | None = None) -> list[Quote]:
    """Cotizaciones de los trimestres a..actual del año (los 4 si es un año pasado).

    No inserta en la base de datos (eso lo hace el CLI); los trimestres cuyo
    archivo no existe (404) se ignoran con log.
    """
    today = today_caracas()
    if year is None:
        year = today.year
    quotes: list[Quote] = []
    for month in QUARTER_START_MONTHS:
        if year == today.year and month > today.month:
            break
        try:
            quotes.extend(_quarter_quotes(year, month))
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            log.info("Sin Excel del BCV para %d-%s (404); ignorado", year, quarter_letter(month))
        except ValueError as exc:
            log.warning("Excel del BCV de %d-%s ilegible: %s", year, quarter_letter(month), exc)
    return quotes
