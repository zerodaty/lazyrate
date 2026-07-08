"""Tests del subcomando `lazyrate now`: snapshot local, sin red."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from lazyrate import cli, store
from lazyrate.providers.base import Quote, now_utc, today_caracas


@pytest.fixture(autouse=True)
def _isolated_xdg(tmp_path, monkeypatch):
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))


def _seed() -> None:
    today = today_caracas()
    fetched = now_utc()
    store.insert_quotes(
        [
            Quote("bcv", "USD", 100.0, fetched, today - timedelta(days=1)),
            Quote("bcv", "USD", 108.0, fetched, today),
            Quote("bcv", "USD", 110.0, fetched, today + timedelta(days=1)),  # "próxima"
            Quote("binance_p2p", "USDT", 130.0, fetched, today),
        ]
    )


def test_now_prints_rates_change_upcoming_and_gap(capsys):
    _seed()
    assert cli.main(["now"]) == 0
    out = capsys.readouterr().out
    assert "BCV USD" in out and "108,0000 Bs" in out
    # La variación usa la tasa vigente (108 vs 100), no la futura
    assert "var. día +8,00%" in out
    assert "próxima 110,0000 Bs" in out
    assert "P2P USDT" in out and "130,0000 Bs" in out
    assert "Brecha BCV↔P2P: +20,37%" in out


def test_now_json_is_machine_readable(capsys):
    _seed()
    assert cli.main(["now", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    pairs = {(p["source"], p["currency"]): p for p in payload["pairs"]}
    assert pairs[("bcv", "USD")]["rate"] == 108.0
    assert pairs[("bcv", "USD")]["day_change_pct"] == pytest.approx(8.0)
    assert pairs[("bcv", "USD")]["upcoming_rate"] == 110.0
    assert pairs[("binance_p2p", "USDT")]["day_change_pct"] is None  # un solo día
    assert payload["gap_bcv_p2p_pct"] == pytest.approx((130 - 108) / 108 * 100, abs=1e-4)


def test_now_source_filter_omits_gap(capsys):
    _seed()
    assert cli.main(["now", "--source", "binance"]) == 0
    out = capsys.readouterr().out
    assert "P2P USDT" in out
    assert "BCV" not in out  # ni el par BCV ni la línea de brecha


def test_now_without_data_fails():
    assert cli.main(["now"]) == 1


def test_now_json_without_data_fails_with_empty_payload(capsys):
    assert cli.main(["now", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["pairs"] == []
