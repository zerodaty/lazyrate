"""Tests del proveedor Binance P2P (sin red: la descarga de páginas se parchea)."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from lazyrate.config import Config
from lazyrate.providers import binance_p2p
from lazyrate.providers.base import today_caracas

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "binance_p2p_page1.json"


@pytest.fixture(autouse=True)
def _isolated_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.fixture()
def page1() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _patch_pages(monkeypatch, responses: list[dict]) -> list[dict]:
    """Sirve `responses` en orden y registra los payloads enviados."""
    payloads: list[dict] = []

    def fake_fetch_page(payload: dict) -> dict:
        payloads.append(payload)
        return responses[min(len(payloads), len(responses)) - 1]

    monkeypatch.setattr(binance_p2p, "_fetch_page", fake_fetch_page)
    return payloads


# ---------------------------------------------------------------- fetch()


def test_fetch_returns_one_quote_from_fixture(monkeypatch, page1):
    cfg = Config()
    cfg.binance.max_ads = 20
    payloads = _patch_pages(monkeypatch, [page1])

    quotes = binance_p2p.BinanceP2PProvider().fetch(cfg)

    assert len(quotes) == 1
    quote = quotes[0]
    prices = [float(ad["adv"]["price"]) for ad in page1["data"]]
    assert min(prices) <= quote.rate <= max(prices)
    assert quote.source == "binance_p2p"
    assert quote.currency == "USDT"
    assert quote.value_date == today_caracas()
    assert quote.fetched_at.tzinfo is not None
    # El IQR (cuartiles interpolados) puede descartar anuncios extremos de la fixture
    assert quote.meta["ads_total"] == 20
    assert 1 <= quote.meta["ads_used"] <= 20
    assert len(payloads) == 1  # página completa pero max_ads ya cubierto


def test_fetch_paginates_until_max_ads(monkeypatch, page1):
    cfg = Config()
    cfg.binance.max_ads = 50
    payloads = _patch_pages(monkeypatch, [page1])  # siempre 20 anuncios por página

    quote = binance_p2p.BinanceP2PProvider().fetch(cfg)[0]

    assert [p["page"] for p in payloads] == [1, 2, 3]
    assert quote.meta["ads_total"] == 50  # recortado a max_ads


def test_fetch_stops_on_short_page_and_skips_bad_ads(monkeypatch, page1):
    short = copy.deepcopy(page1)
    short["data"] = short["data"][:5]
    short["data"][0]["adv"]["price"] = "no-numérico"  # anuncio malformado ignorado
    cfg = Config()
    cfg.binance.max_ads = 100
    payloads = _patch_pages(monkeypatch, [short])

    quote = binance_p2p.BinanceP2PProvider().fetch(cfg)[0]

    assert len(payloads) == 1  # página corta => no pide más
    assert quote.meta["ads_total"] == 4


def test_fetch_raises_without_valid_ads(monkeypatch, page1):
    empty = dict(page1, data=[])
    _patch_pages(monkeypatch, [empty])

    with pytest.raises(RuntimeError, match="anuncios"):
        binance_p2p.BinanceP2PProvider().fetch(Config())


# ---------------------------------------------------------------- payload


def test_build_payload_merchant_only_true():
    cfg = Config()
    cfg.binance.merchant_only = True
    payload = binance_p2p.build_payload(cfg, page=3)
    assert payload == {
        "asset": "USDT",
        "fiat": "VES",
        "tradeType": "SELL",
        "rows": 20,
        "page": 3,
        "publisherType": "merchant",
    }


def test_build_payload_merchant_only_false():
    cfg = Config()
    cfg.binance.merchant_only = False
    assert binance_p2p.build_payload(cfg, page=1)["publisherType"] is None


# ---------------------------------------------------------------- iqr_filter


def test_iqr_filter_small_list_untouched():
    prices = [10.0, 999.0, 1.0]
    assert binance_p2p.iqr_filter(prices) == prices


def test_iqr_filter_drops_outlier():
    # ordenada: q1 = s[1] = 10.1, q3 = s[3] = 10.3, iqr = 0.2 => cotas [9.8, 10.6]
    prices = [10.0, 10.1, 10.2, 10.3, 50.0]
    assert binance_p2p.iqr_filter(prices) == [10.0, 10.1, 10.2, 10.3]


def test_iqr_filter_empty_result_falls_back_to_original():
    # NaN nunca satisface las cotas: el filtro vacía la lista y se devuelve la original
    prices = [math.nan, math.nan, math.nan, math.nan]
    assert binance_p2p.iqr_filter(prices) is prices


# ---------------------------------------------------------------- weighted_average


def test_weighted_average_exact():
    offers = [(10.0, 2.0), (20.0, 1.0), (100.0, 5.0)]
    # solo 10 y 20 aceptados: (10*2 + 20*1) / (2 + 1) = 40/3
    result = binance_p2p.weighted_average(offers, {10.0, 20.0})
    assert result == pytest.approx(40.0 / 3.0)


def test_weighted_average_zero_quantity_falls_back_to_mean():
    offers = [(10.0, 0.0), (20.0, 0.0)]
    assert binance_p2p.weighted_average(offers, {10.0, 20.0}) == pytest.approx(15.0)
