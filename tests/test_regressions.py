"""Regresiones de la revisión adversarial (julio 2026)."""

from __future__ import annotations

import pytest

from lazyrate import config as config_mod


@pytest.fixture(autouse=True)
def _isolated_xdg(tmp_path, monkeypatch):
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))


def test_iqr_filter_drops_extreme_outlier_with_four_prices():
    # Con índices nearest-rank, q3 era el propio máximo y el outlier sobrevivía
    from lazyrate.providers.binance_p2p import iqr_filter

    kept = iqr_filter([100.0, 101.0, 102.0, 10000.0])
    assert kept == [100.0, 101.0, 102.0]


def test_binance_pagination_is_bounded_with_full_invalid_pages(monkeypatch):
    # Páginas llenas de anuncios malformados no deben producir un bucle sin fin
    from lazyrate.providers import binance_p2p

    calls: list[int] = []

    def fake_fetch_page(payload):
        calls.append(payload["page"])
        return {"data": [{"malformado": True}] * binance_p2p.PAGE_SIZE}

    monkeypatch.setattr(binance_p2p, "_fetch_page", fake_fetch_page)
    with pytest.raises(RuntimeError):
        binance_p2p.BinanceP2PProvider().fetch(config_mod.Config())
    assert len(calls) <= 10  # 2 * ceil(max_ads=100 / 20)


def test_bcv_download_rejects_non_xls_response(monkeypatch):
    from lazyrate.providers import bcv

    class FakeResponse:
        def read(self, _n):
            return b"<html><body>mantenimiento</body></html>"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
    with pytest.raises(ValueError):
        bcv.download("https://www.bcv.org.ve/x.xls")


def test_bcv_parse_workbook_discards_corrupt_cache(tmp_path):
    from lazyrate.providers import bcv

    corrupt = tmp_path / "2_1_2a26_otrasmonedas.xls"
    corrupt.write_bytes(b"<html>no soy un xls</html>")
    with pytest.raises(ValueError):
        bcv.parse_workbook(corrupt)
    assert not corrupt.exists()


def test_config_discards_wrong_types():
    path = config_mod.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '[general]\nrefresh_minutes = "veinte"\n\n[bcv]\ncurrencies = [1, 2]\n',
        encoding="utf-8",
    )
    cfg = config_mod.load(create=False)
    assert cfg.general.refresh_minutes == 20
    assert cfg.bcv.currencies == ["USD"]


def test_bar_text_falls_back_on_invalid_format():
    from lazyrate import service

    cfg = config_mod.Config()
    cfg.bar.format = "BCV {bcv_usd"  # llave sin cerrar: ValueError en format_map
    text = service.bar_text(cfg)
    assert "{bcv_usd" not in text  # cayó al formato por defecto sin explotar
