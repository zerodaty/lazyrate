"""Proveedores de tasas. Imports perezosos para no cargar deps que no se usan."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lazyrate.config import Config
    from lazyrate.providers.base import Provider


def get_enabled_providers(cfg: "Config") -> list["Provider"]:
    providers: list[Provider] = []
    if cfg.bcv.enabled:
        from lazyrate.providers.bcv import BcvProvider

        providers.append(BcvProvider())
    if cfg.binance.enabled:
        from lazyrate.providers.binance_p2p import BinanceP2PProvider

        providers.append(BinanceP2PProvider())
    return providers
