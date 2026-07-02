"""Prueba de humo de la TUI: siembra datos locales y navega con pilot (sin red)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta


def _isolate_xdg(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _seed_history() -> None:
    from lazyrate import store
    from lazyrate.providers.base import Quote

    start = date(2026, 6, 1)
    fetched = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    quotes = [
        Quote("bcv", "USD", 100.0 + i, fetched, start + timedelta(days=i)) for i in range(10)
    ]
    quotes += [
        Quote("binance_p2p", "USDT", 112.0 + i, fetched, start + timedelta(days=7 + i))
        for i in range(3)
    ]
    assert store.insert_quotes(quotes) == 13


def test_tui_smoke(tmp_path, monkeypatch):
    _isolate_xdg(tmp_path, monkeypatch)
    _seed_history()

    from lazyrate.tui.app import LazyrateApp
    from lazyrate.tui.widgets import RateChart, StatsPanel

    async def drive() -> None:
        app = LazyrateApp()
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert ("bcv", "USD") in app.pairs
            assert ("binance_p2p", "USDT") in app.pairs

            await pilot.press("7")
            assert app.range_days == 7

            await pilot.press("b")
            assert app.compare is True

            await pilot.press("a")
            assert app.range_days == 0
            await pilot.pause()

            panel = app.query_one(StatsPanel)
            assert "Actual" in panel.plain_text
            assert "Tendencia 7d" in panel.plain_text
            assert "Brecha BCV↔P2P" in panel.plain_text

            chart = app.query_one(RateChart)
            assert "Evolución (todo)" in str(chart.border_title)

    asyncio.run(drive())
