"""Tests del proveedor BCV (sin red: fixture real + monkeypatch de la descarga)."""

from __future__ import annotations

import os
import time
import urllib.error
from datetime import UTC, date
from pathlib import Path

import pytest

from lazyrate.config import BCV_CURRENCIES, Config
from lazyrate.providers import bcv
from lazyrate.providers.base import now_utc

FIXTURE = Path(__file__).parent / "fixtures" / "2_1_2a26_otrasmonedas.xls"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Aísla las rutas XDG en tmp_path y bloquea toda petición de red."""
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))

    def _blocked(*args, **kwargs):
        raise AssertionError("Los tests no deben hacer peticiones de red")

    monkeypatch.setattr("urllib.request.urlopen", _blocked)


class FakeSheet:
    """Hoja mínima con la interfaz de xlrd usada por el parser."""

    def __init__(self, name: str, rows: list[list]):
        self.name = name
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max(len(row) for row in rows)

    def cell_value(self, rowx: int, colx: int):
        row = self._rows[rowx]
        return row[colx] if colx < len(row) else ""


def _sheet(value_date_cell: str, data_rows: list[list]) -> FakeSheet:
    rows: list[list] = [[] for _ in range(10)]
    rows[4] = ["", "", "", value_date_cell]
    rows.extend(data_rows)
    return FakeSheet("01072026", rows)


# --- URL / trimestres ---------------------------------------------------------


def test_quarter_letter_by_month():
    assert bcv.quarter_letter(2) == "a"  # febrero
    assert bcv.quarter_letter(7) == "c"  # julio
    assert [bcv.quarter_letter(m) for m in (1, 3, 4, 6, 7, 9, 10, 12)] == list("aabbccdd")


def test_quarter_url():
    assert bcv.quarter_url(2026, 2) == (
        "https://www.bcv.org.ve/sites/default/files/EstadisticasGeneral"
        "/2_1_2a26_otrasmonedas.xls"
    )
    assert bcv.quarter_url(2026, 7).endswith("/2_1_2c26_otrasmonedas.xls")


def test_previous_quarter_crosses_year():
    assert bcv.previous_quarter(2026, 1) == (2025, 12)  # enero → trimestre d del año anterior
    assert bcv.quarter_filename(2025, 12) == "2_1_2d25_otrasmonedas.xls"
    assert bcv.previous_quarter(2026, 7) == (2026, 6)
    assert bcv.quarter_letter(6) == "b"


# --- Parseo de la fixture real ------------------------------------------------


def test_parse_workbook_full_fixture():
    quotes = bcv.parse_workbook(FIXTURE)
    assert len(quotes) == 37 * len(BCV_CURRENCIES)  # 37 hojas x 5 monedas
    for currency in BCV_CURRENCIES:
        assert sum(1 for q in quotes if q.currency == currency) == 37
    assert all(q.source == "bcv" for q in quotes)
    assert all(q.fetched_at.tzinfo is not None and q.fetched_at.utcoffset() is not None
               for q in quotes)
    assert min(q.value_date for q in quotes) == date(2026, 1, 5)
    assert max(q.value_date for q in quotes) == date(2026, 3, 2)


def test_parse_workbook_usd_latest_sheet():
    quotes = bcv.parse_workbook(FIXTURE)
    (usd,) = [q for q in quotes if q.currency == "USD" and q.meta["sheet"] == "27022026"]
    assert usd.rate == 419.9873
    assert usd.value_date == date(2026, 3, 2)  # fecha valor, no la fecha operación de la hoja
    assert usd.fetched_at.tzinfo is UTC


# --- Regex de fecha valor y celdas defectuosas --------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Fecha Valor:  02/07/2026",
        "Fecha Valor : 02/07/2026",
        "Fecha Valor:02/07/2026",
        "Fecha Valor  :\t 02/07/2026",
    ],
)
def test_value_date_regex_variable_spacing(text):
    sheet = _sheet(text, [["", "USD", "", "", "", "", 420.5]])
    (quote,) = bcv._parse_sheet(sheet, now_utc())
    assert quote.value_date == date(2026, 7, 2)


def test_sheet_without_value_date_is_skipped():
    sheet = _sheet("cualquier otra cosa", [["", "USD", "", "", "", "", 420.5]])
    assert bcv._parse_sheet(sheet, now_utc()) == []


def test_dashes_row_does_not_crash():
    sheet = _sheet(
        "Fecha Valor:  02/07/2026",
        [
            ["", "PTR", "", "", "", "", "----------------"],
            ["", "USD", "", "", "", "", "----------------"],  # defensivo aunque sea rastreada
            ["", "EUR", "", "", "", "", 495.60601336],
        ],
    )
    quotes = bcv._parse_sheet(sheet, now_utc())
    assert [q.currency for q in quotes] == ["EUR"]
    assert quotes[0].rate == 495.606  # round(value, 4)


# --- fetch(): trimestre actual + fallback al anterior -------------------------


def _patched_fetch_workbook(monkeypatch, calls, fail_404: set[tuple[int, int]] = frozenset()):
    def fake(year: int, month: int):
        calls.append((year, month))
        if (year, month) in fail_404:
            raise urllib.error.HTTPError(bcv.quarter_url(year, month), 404, "Not Found", None, None)
        return FIXTURE

    monkeypatch.setattr(bcv, "fetch_workbook", fake)


def test_fetch_only_current_quarter_when_it_covers_today(monkeypatch):
    calls: list[tuple[int, int]] = []
    _patched_fetch_workbook(monkeypatch, calls)
    monkeypatch.setattr(bcv, "today_caracas", lambda: date(2026, 2, 1))
    quotes = bcv.BcvProvider().fetch(Config())
    assert calls == [(2026, 2)]
    assert len(quotes) == 37 * len(BCV_CURRENCIES)


def test_fetch_falls_back_when_min_value_date_is_future(monkeypatch):
    # La fixture solo trae fechas valor desde el 05/01: con hoy=02/01 debe bajar
    # también el trimestre anterior (d del año pasado por el cruce de año).
    calls: list[tuple[int, int]] = []
    _patched_fetch_workbook(monkeypatch, calls)
    monkeypatch.setattr(bcv, "today_caracas", lambda: date(2026, 1, 2))
    quotes = bcv.BcvProvider().fetch(Config())
    assert calls == [(2026, 1), (2025, 12)]
    assert len(quotes) == 2 * 37 * len(BCV_CURRENCIES)


def test_fetch_falls_back_when_current_quarter_404(monkeypatch):
    calls: list[tuple[int, int]] = []
    _patched_fetch_workbook(monkeypatch, calls, fail_404={(2026, 7)})
    monkeypatch.setattr(bcv, "today_caracas", lambda: date(2026, 7, 1))
    quotes = bcv.BcvProvider().fetch(Config())
    assert calls == [(2026, 7), (2026, 6)]
    assert len(quotes) == 37 * len(BCV_CURRENCIES)


# --- backfill -----------------------------------------------------------------


def test_backfill_current_year_ignores_404(monkeypatch):
    calls: list[tuple[int, int]] = []
    _patched_fetch_workbook(monkeypatch, calls, fail_404={(2026, 7)})
    monkeypatch.setattr(bcv, "today_caracas", lambda: date(2026, 7, 1))
    quotes = bcv.backfill(Config())
    assert calls == [(2026, 1), (2026, 4), (2026, 7)]  # trimestres a..actual
    assert len(quotes) == 2 * 37 * len(BCV_CURRENCIES)  # el 404 se ignora


def test_backfill_past_year_uses_four_quarters(monkeypatch):
    calls: list[tuple[int, int]] = []
    _patched_fetch_workbook(monkeypatch, calls)
    monkeypatch.setattr(bcv, "today_caracas", lambda: date(2026, 7, 1))
    bcv.backfill(Config(), year=2025)
    assert calls == [(2025, 1), (2025, 4), (2025, 7), (2025, 10)]


# --- caché --------------------------------------------------------------------


def test_fetch_workbook_uses_fresh_cache(monkeypatch, tmp_path):
    downloads: list[str] = []

    def fake_download(url: str) -> bytes:
        downloads.append(url)
        return FIXTURE.read_bytes()

    monkeypatch.setattr(bcv, "download", fake_download)
    path1 = bcv.fetch_workbook(2026, 1)
    path2 = bcv.fetch_workbook(2026, 1)
    assert path1 == path2
    assert downloads == [bcv.quarter_url(2026, 1)]  # la segunda llamada reusa la caché
    assert path1.read_bytes() == FIXTURE.read_bytes()
    assert str(path1).startswith(str(tmp_path))  # caché bajo el XDG_CACHE_HOME aislado


def test_fetch_workbook_falls_back_to_stale_cache(monkeypatch):
    monkeypatch.setattr(bcv, "download", lambda url: FIXTURE.read_bytes())
    path = bcv.fetch_workbook(2026, 1)
    # Envejece la caché más allá de las 6 horas y hace fallar la descarga
    old = time.time() - bcv.CACHE_MAX_AGE_SECONDS - 60
    os.utime(path, (old, old))

    def failing(url: str) -> bytes:
        raise urllib.error.URLError("caída simulada")

    monkeypatch.setattr(bcv, "download", failing)
    assert bcv.fetch_workbook(2026, 1) == path  # usa la caché vieja con warning
