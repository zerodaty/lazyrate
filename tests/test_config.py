"""Tests de lazyrate.config: load()/save() sobre un HOME XDG temporal."""

from __future__ import annotations

import pytest

from lazyrate import config as config_mod


@pytest.fixture(autouse=True)
def xdg_tmp(tmp_path, monkeypatch):
    """Aísla todas las rutas XDG en tmp_path para no tocar datos reales."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


def test_load_without_file_creates_defaults():
    path = config_mod.config_path()
    assert not path.exists()
    cfg = config_mod.load()
    assert path.exists()
    assert cfg == config_mod.Config()
    # El TOML escrito se puede volver a leer y da lo mismo
    assert config_mod.load() == cfg


def test_load_without_file_create_false_does_not_write():
    cfg = config_mod.load(create=False)
    assert cfg == config_mod.Config()
    assert not config_mod.config_path().exists()


def test_save_load_roundtrip():
    cfg = config_mod.Config()
    cfg.general.refresh_minutes = 5
    cfg.general.decimals = 4
    cfg.bar.format = "USD {bcv_usd}"
    cfg.bar.stale_mark = False
    cfg.bcv.currencies = ["USD", "EUR"]
    cfg.bcv.publish_hour = 20
    cfg.binance.enabled = False
    cfg.binance.max_ads = 40
    config_mod.save(cfg)
    assert config_mod.load() == cfg


def test_unknown_keys_are_ignored():
    config_mod.config_dir().mkdir(parents=True)
    config_mod.config_path().write_text(
        """
[general]
refresh_minutes = 7
totally_unknown = "whatever"

[bar]
another_unknown = 42

[future_section]
key = true
""",
        encoding="utf-8",
    )
    cfg = config_mod.load()
    assert cfg.general.refresh_minutes == 7
    assert cfg.general.decimals == 2  # default intacto
    assert cfg.bar.format == config_mod.BarCfg().format


def test_corrupt_toml_falls_back_to_defaults():
    config_mod.config_dir().mkdir(parents=True)
    config_mod.config_path().write_text("esto no es [[[ toml válido", encoding="utf-8")
    assert config_mod.load() == config_mod.Config()


def test_partial_sections_use_defaults_for_rest():
    config_mod.config_dir().mkdir(parents=True)
    config_mod.config_path().write_text(
        """
[general]
refresh_minutes = 99
""",
        encoding="utf-8",
    )
    cfg = config_mod.load()
    assert cfg.general.refresh_minutes == 99
    assert cfg.bar == config_mod.BarCfg()
    assert cfg.bcv == config_mod.BcvCfg()
    assert cfg.binance == config_mod.BinanceCfg()


def test_xdg_paths_use_env(tmp_path):
    assert config_mod.config_dir() == tmp_path / "config" / "lazyrate"
    assert config_mod.data_dir() == tmp_path / "data" / "lazyrate"
    assert config_mod.cache_dir() == tmp_path / "cache" / "lazyrate"
    assert config_mod.state_dir() == tmp_path / "state" / "lazyrate"
