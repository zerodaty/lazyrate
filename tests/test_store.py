"""Tests de lazyrate.store sobre una base SQLite en un directorio XDG temporal."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from lazyrate import store
from lazyrate.providers.base import Quote, today_caracas


@pytest.fixture(autouse=True)
def xdg_tmp(tmp_path, monkeypatch):
    """Aísla todas las rutas XDG en tmp_path para no tocar datos reales."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


def _quote(
    source: str = "bcv",
    currency: str = "USD",
    rate: float = 100.0,
    value_date: date | None = None,
    fetched_at: datetime | None = None,
    meta: dict | None = None,
) -> Quote:
    value_date = value_date or today_caracas()
    return Quote(
        source=source,
        currency=currency,
        rate=rate,
        fetched_at=fetched_at or datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
        value_date=value_date,
        meta=meta or {},
    )


def _count_rows(source: str, currency: str) -> int:
    with sqlite3.connect(store.db_path()) as conn:
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM rates WHERE source = ? AND currency = ?", (source, currency)
        ).fetchone()
    return n


# --- insert_quotes ---


def test_insert_bcv_is_idempotent_per_value_date():
    day = date(2026, 6, 10)
    first = _quote(value_date=day, fetched_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC))
    dupe = _quote(value_date=day, rate=101.0, fetched_at=datetime(2026, 6, 10, 18, 0, tzinfo=UTC))
    assert store.insert_quotes([first]) == 1
    assert store.insert_quotes([dupe]) == 0
    assert _count_rows("bcv", "USD") == 1
    row = store.latest("bcv", "USD")
    assert row is not None
    assert row.rate == 100.0  # se conserva la primera


def test_insert_binance_is_not_idempotent_intraday():
    day = date(2026, 6, 10)
    q1 = _quote(
        source="binance_p2p",
        currency="USDT",
        rate=130.0,
        value_date=day,
        fetched_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
    )
    q2 = _quote(
        source="binance_p2p",
        currency="USDT",
        rate=131.0,
        value_date=day,
        fetched_at=datetime(2026, 6, 10, 15, 0, tzinfo=UTC),
    )
    assert store.insert_quotes([q1, q2]) == 2
    assert _count_rows("binance_p2p", "USDT") == 2


def test_insert_empty_returns_zero():
    assert store.insert_quotes([]) == 0


def test_meta_roundtrip():
    store.insert_quotes(
        [_quote(source="binance_p2p", currency="USDT", meta={"ads_used": 80, "ads_total": 100})]
    )
    row = store.latest("binance_p2p", "USDT")
    assert row is not None
    assert row.meta == {"ads_used": 80, "ads_total": 100}


# --- daily_series ---


def test_daily_series_binance_takes_last_sample_of_day():
    day = date(2026, 6, 10)
    samples = [
        _quote(
            source="binance_p2p",
            currency="USDT",
            rate=130.0,
            value_date=day,
            fetched_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        ),
        _quote(
            source="binance_p2p",
            currency="USDT",
            rate=134.0,
            value_date=day,
            fetched_at=datetime(2026, 6, 10, 20, 0, tzinfo=UTC),
        ),
        _quote(
            source="binance_p2p",
            currency="USDT",
            rate=132.0,
            value_date=day,
            fetched_at=datetime(2026, 6, 10, 16, 0, tzinfo=UTC),
        ),
    ]
    store.insert_quotes(samples)
    assert store.daily_series("binance_p2p", "USDT") == [(day, 134.0)]


def test_daily_series_ordered_and_windowed():
    today = today_caracas()
    store.insert_quotes(
        [
            _quote(value_date=today - timedelta(days=40), rate=90.0),
            _quote(value_date=today - timedelta(days=2), rate=99.0),
            _quote(value_date=today - timedelta(days=1), rate=100.0),
        ]
    )
    assert store.daily_series("bcv", "USD") == [
        (today - timedelta(days=40), 90.0),
        (today - timedelta(days=2), 99.0),
        (today - timedelta(days=1), 100.0),
    ]
    assert store.daily_series("bcv", "USD", days=7) == [
        (today - timedelta(days=2), 99.0),
        (today - timedelta(days=1), 100.0),
    ]


# --- latest / upcoming (tasa de mañana) ---


def test_latest_on_or_before_excludes_tomorrow_and_upcoming_returns_it():
    today = today_caracas()
    tomorrow = today + timedelta(days=1)
    store.insert_quotes(
        [
            _quote(value_date=today, rate=108.0),
            _quote(value_date=tomorrow, rate=109.0),
        ]
    )
    current = store.latest("bcv", "USD", on_or_before=today)
    assert current is not None
    assert (current.value_date, current.rate) == (today, 108.0)

    # Sin filtro, latest devuelve la fecha valor más nueva (la de mañana)
    newest = store.latest("bcv", "USD")
    assert newest is not None
    assert newest.value_date == tomorrow

    upcoming = store.upcoming("bcv", "USD", after=today)
    assert upcoming is not None
    assert (upcoming.value_date, upcoming.rate) == (tomorrow, 109.0)


def test_latest_missing_returns_none():
    assert store.latest("bcv", "EUR") is None
    assert store.upcoming("bcv", "EUR", after=today_caracas()) is None


# --- sources_with_data ---


def test_sources_with_data():
    assert store.sources_with_data() == []
    store.insert_quotes(
        [
            _quote(source="binance_p2p", currency="USDT", rate=130.0),
            _quote(source="bcv", currency="USD", rate=108.0),
        ]
    )
    assert store.sources_with_data() == [("bcv", "USD"), ("binance_p2p", "USDT")]


# --- purge ---


def test_purge_compacts_old_intraday_to_one_row_per_day():
    today = today_caracas()
    old_day = today - timedelta(days=45)  # más viejo que la ventana intradía de 30 días
    store.insert_quotes(
        [
            _quote(
                source="binance_p2p",
                currency="USDT",
                rate=120.0,
                value_date=old_day,
                fetched_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            ),
            _quote(
                source="binance_p2p",
                currency="USDT",
                rate=125.0,
                value_date=old_day,
                fetched_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
            ),
        ]
    )
    removed = store.purge(retention_days=365)
    assert removed == 1
    assert _count_rows("binance_p2p", "USDT") == 1
    row = store.latest("binance_p2p", "USDT")
    assert row is not None
    assert row.rate == 125.0  # sobrevive la última muestra del día


def test_purge_keeps_recent_intraday_samples():
    today = today_caracas()
    for hour in (12, 18):
        store.insert_quotes(
            [
                _quote(
                    source="binance_p2p",
                    currency="USDT",
                    rate=130.0 + hour,
                    value_date=today,
                    fetched_at=datetime(2026, 6, 15, hour, 0, tzinfo=UTC),
                )
            ]
        )
    assert store.purge(retention_days=365) == 0
    assert _count_rows("binance_p2p", "USDT") == 2


def test_purge_respects_retention_days():
    today = today_caracas()
    store.insert_quotes(
        [
            _quote(value_date=today - timedelta(days=20), rate=90.0),
            _quote(value_date=today - timedelta(days=5), rate=100.0),
        ]
    )
    removed = store.purge(retention_days=10)
    assert removed == 1
    assert _count_rows("bcv", "USD") == 1
    series = store.daily_series("bcv", "USD")
    assert series == [(today - timedelta(days=5), 100.0)]
