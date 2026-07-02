"""Persistencia del histórico de tasas en SQLite (~/.local/share/lazyrate/history.db)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from lazyrate.config import data_dir
from lazyrate.providers.base import Quote, today_caracas

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rates (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    currency    TEXT NOT NULL,
    rate        REAL NOT NULL,
    fetched_at  TEXT NOT NULL,
    value_date  TEXT NOT NULL,
    meta        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bcv_day
    ON rates(source, currency, value_date) WHERE source = 'bcv';
CREATE INDEX IF NOT EXISTS ix_lookup
    ON rates(source, currency, value_date, fetched_at);
"""

_COLUMNS = "source, currency, rate, fetched_at, value_date, meta"

# Las muestras intradía de Binance más viejas que esto se compactan a 1 fila/día
_INTRADAY_KEEP_DAYS = 30


@dataclass(frozen=True, slots=True)
class RateRow:
    source: str
    currency: str
    rate: float
    fetched_at: datetime
    value_date: date
    meta: dict


def db_path() -> Path:
    return data_dir() / "history.db"


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def _row(raw: tuple) -> RateRow:
    source, currency, rate, fetched_at, value_date, meta = raw
    return RateRow(
        source=source,
        currency=currency,
        rate=rate,
        fetched_at=datetime.fromisoformat(fetched_at),
        value_date=date.fromisoformat(value_date),
        meta=json.loads(meta) if meta else {},
    )


def insert_quotes(quotes: Iterable[Quote]) -> int:
    """Inserta cotizaciones; las de BCV son idempotentes por (moneda, día valor)."""
    rows = [
        (
            q.source,
            q.currency,
            q.rate,
            q.fetched_at.isoformat(),
            q.value_date.isoformat(),
            json.dumps(q.meta, ensure_ascii=False) if q.meta else None,
        )
        for q in quotes
    ]
    if not rows:
        return 0
    with closing(_connect()) as conn, conn:
        cur = conn.executemany(
            f"INSERT OR IGNORE INTO rates ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)", rows
        )
        return max(cur.rowcount, 0)


def latest(source: str, currency: str, on_or_before: date | None = None) -> RateRow | None:
    query = f"SELECT {_COLUMNS} FROM rates WHERE source = ? AND currency = ?"
    params: list = [source, currency]
    if on_or_before is not None:
        query += " AND value_date <= ?"
        params.append(on_or_before.isoformat())
    query += " ORDER BY value_date DESC, fetched_at DESC LIMIT 1"
    with closing(_connect()) as conn:
        raw = conn.execute(query, params).fetchone()
    return _row(raw) if raw else None


def upcoming(source: str, currency: str, after: date) -> RateRow | None:
    """Primera tasa con fecha valor futura (p.ej. la 'tasa de mañana' del BCV)."""
    query = (
        f"SELECT {_COLUMNS} FROM rates WHERE source = ? AND currency = ? AND value_date > ?"
        " ORDER BY value_date ASC, fetched_at DESC LIMIT 1"
    )
    with closing(_connect()) as conn:
        raw = conn.execute(query, (source, currency, after.isoformat())).fetchone()
    return _row(raw) if raw else None


def daily_series(source: str, currency: str, days: int | None = None) -> list[tuple[date, float]]:
    """Serie diaria (fecha valor, tasa); para Binance toma la última muestra de cada día."""
    query = "SELECT value_date, rate, MAX(fetched_at) FROM rates WHERE source = ? AND currency = ?"
    params: list = [source, currency]
    if days is not None:
        query += " AND value_date >= ?"
        params.append((today_caracas() - timedelta(days=days)).isoformat())
    query += " GROUP BY value_date ORDER BY value_date"
    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [(date.fromisoformat(vd), rate) for vd, rate, _ in rows]


def sources_with_data() -> list[tuple[str, str]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT DISTINCT source, currency FROM rates ORDER BY source, currency"
        ).fetchall()
    return [(s, c) for s, c in rows]


def purge(retention_days: int = 365) -> int:
    """Borra lo más viejo que retention_days y compacta el intradía de Binance a 1 fila/día."""
    cutoff_all = (today_caracas() - timedelta(days=retention_days)).isoformat()
    cutoff_intraday = (today_caracas() - timedelta(days=_INTRADAY_KEEP_DAYS)).isoformat()
    with closing(_connect()) as conn, conn:
        removed = conn.execute(
            """
            DELETE FROM rates
            WHERE source = 'binance_p2p' AND value_date < ?
              AND fetched_at <> (
                  SELECT MAX(r2.fetched_at) FROM rates r2
                  WHERE r2.source = rates.source AND r2.currency = rates.currency
                        AND r2.value_date = rates.value_date)
            """,
            (cutoff_intraday,),
        ).rowcount
        removed += conn.execute(
            "DELETE FROM rates WHERE value_date < ?", (cutoff_all,)
        ).rowcount
    return removed
