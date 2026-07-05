"""Orquestación: fetch de proveedores → validación → persistencia; texto de la barra."""

from __future__ import annotations

import logging

from lazyrate import store
from lazyrate.config import BarCfg, Config
from lazyrate.format import format_rate
from lazyrate.providers import get_enabled_providers
from lazyrate.providers.base import Quote, now_utc, today_caracas, validate_quote

log = logging.getLogger(__name__)


def fetch_and_store(cfg: Config, only_source: str | None = None) -> list[Quote]:
    """Consulta los proveedores habilitados, valida y guarda. Devuelve lo aceptado.

    Nunca lanza por fallos de un proveedor: cada uno se aísla y se loguea, de modo
    que una caída del BCV no impide actualizar Binance (y viceversa).
    """
    accepted: list[Quote] = []
    for provider in get_enabled_providers(cfg):
        if only_source and provider.name != only_source:
            continue
        try:
            fetched = provider.fetch(cfg)
        except Exception:
            log.exception("Fallo consultando %s", provider.name)
            continue
        for quote in fetched:
            ref = store.latest(quote.source, quote.currency)
            if validate_quote(
                quote,
                ref.rate if ref else None,
                ref.value_date if ref else None,
            ):
                accepted.append(quote)
    inserted = store.insert_quotes(accepted)
    if accepted:
        log.info("Fetch: %d cotizaciones aceptadas, %d nuevas", len(accepted), inserted)
    return accepted


class _MissingValue(dict):
    def __missing__(self, key: str) -> str:
        return "…"


def enabled_pairs(cfg: Config) -> list[tuple[str, str]]:
    """Pares (fuente, moneda) habilitados por configuración."""
    pairs: list[tuple[str, str]] = []
    if cfg.bcv.enabled:
        pairs.extend(("bcv", c) for c in cfg.bcv.currencies)
    if cfg.binance.enabled:
        pairs.append(("binance_p2p", cfg.binance.asset))
    return pairs


def available_pairs(cfg: Config) -> list[tuple[str, str]]:
    """Pares habilitados por config más los que ya tienen datos guardados.

    Une la configuración vigente con lo que hay en la base: una fuente que se
    deshabilitó pero cuyo histórico sigue guardado sigue siendo consultable.
    """
    pairs = list(enabled_pairs(cfg))
    for pair in store.sources_with_data():
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def latest_rate(source: str, currency: str) -> store.RateRow | None:
    """Tasa vigente de un par; para BCV se acota a la fecha valor de hoy o antes."""
    on_or_before = today_caracas() if source == "bcv" else None
    return store.latest(source, currency, on_or_before=on_or_before)


def bar_values(cfg: Config) -> dict[str, str]:
    """Valores formateados para los placeholders del formato de la barra."""
    today = today_caracas()
    values: dict[str, str] = {}
    for source, currency in enabled_pairs(cfg):
        on_or_before = today if source == "bcv" else None
        row = store.latest(source, currency, on_or_before=on_or_before)
        if row is None:
            continue
        prefix = "bcv" if source == "bcv" else "binance"
        values[f"{prefix}_{currency.lower()}"] = format_rate(row.rate, cfg.general.decimals)
    return values


def bar_text(cfg: Config) -> str:
    values = _MissingValue(bar_values(cfg))
    try:
        return cfg.bar.format.format_map(values)
    except Exception:  # noqa: BLE001 — formato editable por el usuario: nunca tumbar al indicador
        log.warning("Formato de barra inválido (%r); usando el formato por defecto", cfg.bar.format)
        return BarCfg().format.format_map(values)


def newest_fetch_age_minutes(cfg: Config) -> float | None:
    """Minutos desde el fetch más reciente entre las fuentes habilitadas (None sin datos)."""
    newest = None
    for source, currency in enabled_pairs(cfg):
        row = store.latest(source, currency)
        if row and (newest is None or row.fetched_at > newest):
            newest = row.fetched_at
    if newest is None:
        return None
    return (now_utc() - newest).total_seconds() / 60
