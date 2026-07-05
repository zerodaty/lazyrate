"""Conversión de montos entre divisa y bolívares, y disparidad entre dos tasas.

Lógica pura (solo stdlib), sin I/O ni UI: espejo de ``stats.py``. Una tasa es
siempre "Bs por 1 unidad de la divisa", igual que ``Quote.rate``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Leg:
    """Un lado de la comparación: una fuente/moneda con su tasa vigente."""

    source: str  # "bcv" | "binance_p2p"
    currency: str  # "USD", "EUR", "USDT"...
    rate: float  # Bs por 1 unidad de la divisa


def to_bs(amount: float, rate: float) -> float:
    """Divisa → Bs: cuántos bolívares son ``amount`` unidades a esta tasa."""
    return amount * rate


def to_currency(bs: float, rate: float) -> float:
    """Bs → Divisa: cuántas unidades de divisa son ``bs`` bolívares a esta tasa."""
    return bs / rate if rate else 0.0


def disparity_pct(a: float, b: float) -> float | None:
    """Disparidad de ``b`` respecto a ``a`` en %: ``(b - a) / a * 100``.

    Devuelve ``None`` si ``a`` es 0 (evita la división por cero), igual que
    ``stats.day_change_pct`` y ``stats.gap_pct``.
    """
    return (b - a) / a * 100 if a else None
