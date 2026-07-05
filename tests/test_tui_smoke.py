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

            panel = app.query_one("#stats", StatsPanel)
            assert "Actual" in panel.plain_text
            assert "Tendencia 7d" in panel.plain_text
            assert "Brecha BCV↔P2P" in panel.plain_text

            chart = app.query_one(RateChart)
            assert "Evolución (todo)" in str(chart.border_title)

    asyncio.run(drive())


def test_calculator_smoke(tmp_path, monkeypatch):
    _isolate_xdg(tmp_path, monkeypatch)
    _seed_history()

    from textual.widgets import Select, TabbedContent

    from lazyrate.tui.app import LazyrateApp
    from lazyrate.tui.widgets import RateChart, StatsPanel

    async def drive() -> None:
        app = LazyrateApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            tabs = app.query_one("#left-tabs", TabbedContent)
            assert tabs.active == "tab-fuentes"  # arranca en Fuentes

            await pilot.press("equals_sign")  # atajo: abre la pestaña Calculadora
            await pilot.pause()
            assert tabs.active == "tab-calc"

            amount = app.query_one("#calc-amount")
            amount.value = "100"
            await pilot.pause()

            # Resultados en la columna izquierda (form + resultado)
            result = app.query_one("#calc-result", StatsPanel)
            assert "Bs" in result.plain_text
            assert "BCV · USD" in result.plain_text
            assert "Binance P2P · USDT" in result.plain_text
            assert "Disparidad" in result.plain_text

            # Panel derecho: gráfica de comparación A vs B + estadísticas de brecha
            chart = app.query_one(RateChart)
            assert "Comparación" in str(chart.border_title)
            comp = app.query_one("#stats", StatsPanel)
            assert "Disparidad B vs A" in comp.plain_text

            # El modo inverso (Bs→Divisa) solo cambia los resultados de la izquierda
            app.query_one("#calc-direction", Select).value = "to_currency"
            await pilot.pause()
            assert "USDT" in result.plain_text

            # Esc vuelve a Fuentes aunque el foco esté en el campo Monto
            await pilot.press("escape")
            await pilot.pause()
            assert tabs.active == "tab-fuentes"
            assert "Evolución" in str(chart.border_title)

    asyncio.run(drive())
