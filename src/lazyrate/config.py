"""Configuración de lazyrate: TOML en ~/.config/lazyrate/config.toml y rutas XDG."""

from __future__ import annotations

import dataclasses
import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

APP_NAME = "lazyrate"

# Monedas que publica el Excel "otras monedas" del BCV
BCV_CURRENCIES = ("USD", "EUR", "CNY", "TRY", "RUB")

log = logging.getLogger(__name__)


def _xdg_root(env_var: str, default: str) -> Path:
    base = os.environ.get(env_var, "")
    return Path(base) if base else Path.home() / default


def xdg_config_root() -> Path:
    return _xdg_root("XDG_CONFIG_HOME", ".config")


def config_dir() -> Path:
    return xdg_config_root() / APP_NAME


def data_dir() -> Path:
    return _xdg_root("XDG_DATA_HOME", ".local/share") / APP_NAME


def cache_dir() -> Path:
    return _xdg_root("XDG_CACHE_HOME", ".cache") / APP_NAME


def state_dir() -> Path:
    return _xdg_root("XDG_STATE_HOME", ".local/state") / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class GeneralCfg:
    refresh_minutes: int = 20
    decimals: int = 2
    retention_days: int = 365


@dataclass
class BarCfg:
    # Placeholders disponibles: {bcv_usd}, {bcv_eur}, ..., {binance_usdt}
    format: str = "BCV {bcv_usd} | P2P {binance_usdt}"
    stale_mark: bool = True


@dataclass
class BcvCfg:
    enabled: bool = True
    currencies: list[str] = field(default_factory=lambda: ["USD"])
    # Hora (America/Caracas) desde la que se busca también la tasa del día siguiente
    publish_hour: int = 18


@dataclass
class BinanceCfg:
    enabled: bool = True
    asset: str = "USDT"
    trade_type: str = "SELL"
    merchant_only: bool = True
    max_ads: int = 100


@dataclass
class Config:
    general: GeneralCfg = field(default_factory=GeneralCfg)
    bar: BarCfg = field(default_factory=BarCfg)
    bcv: BcvCfg = field(default_factory=BcvCfg)
    binance: BinanceCfg = field(default_factory=BinanceCfg)


def _section(cls, data: dict):
    """Construye la sección ignorando claves desconocidas y valores de tipo incorrecto.

    Un TOML editado a mano con p.ej. refresh_minutes = "veinte" no debe tumbar
    al indicador al arrancar: se descarta el valor y se usa el default.
    """
    defaults = cls()
    known = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - known
    if unknown:
        log.debug("Claves de configuración ignoradas en [%s]: %s", cls.__name__, unknown)
    kwargs = {}
    for key, value in data.items():
        if key not in known:
            continue
        default = getattr(defaults, key)
        if isinstance(default, bool):
            valid = isinstance(value, bool)
        elif isinstance(default, int):
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif isinstance(default, str):
            valid = isinstance(value, str)
        elif isinstance(default, list):
            valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
        else:
            valid = True
        if not valid:
            log.warning(
                "Valor inválido para %s (%r); usando el default %r", key, value, default
            )
            continue
        kwargs[key] = value
    return cls(**kwargs)


def load(create: bool = True) -> Config:
    """Lee la configuración; si no existe (y create=True) escribe una con los defaults."""
    path = config_path()
    if not path.exists():
        cfg = Config()
        if create:
            try:
                save(cfg)
            except OSError as exc:
                log.warning("No se pudo crear %s: %s", path, exc)
        return cfg
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("No se pudo leer %s (%s); usando valores por defecto", path, exc)
        return Config()
    return Config(
        general=_section(GeneralCfg, data.get("general", {})),
        bar=_section(BarCfg, data.get("bar", {})),
        bcv=_section(BcvCfg, data.get("bcv", {})),
        binance=_section(BinanceCfg, data.get("binance", {})),
    )


def save(cfg: Config) -> None:
    """Escritura atómica: volcado a .tmp en el mismo directorio + os.replace."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".toml.tmp")
    with tmp.open("wb") as fh:
        tomli_w.dump(dataclasses.asdict(cfg), fh)
    os.replace(tmp, path)
