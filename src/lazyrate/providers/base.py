"""Contrato común de los proveedores de tasas y validación de datos."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from lazyrate.config import Config

log = logging.getLogger(__name__)

CARACAS_TZ = ZoneInfo("America/Caracas")

HTTP_TIMEOUT = 30  # segundos, para todo urlopen
MAX_RESPONSE_BYTES = 5_000_000

RATE_MIN = 0.01
RATE_MAX = 1e7
MAX_DEVIATION = 0.5  # ±50% respecto al último valor guardado
DEVIATION_WINDOW_DAYS = 7  # la desviación solo se compara contra valores de fechas próximas


def today_caracas() -> date:
    return datetime.now(CARACAS_TZ).date()


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Quote:
    source: str  # "bcv" | "binance_p2p"
    currency: str  # "USD", "EUR", "USDT"...
    rate: float  # Bs por 1 unidad
    fetched_at: datetime  # UTC aware
    value_date: date  # día al que aplica la tasa (America/Caracas)
    meta: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def fetch(self, cfg: "Config") -> list[Quote]: ...


def validate_quote(
    quote: Quote,
    last_rate: float | None = None,
    last_value_date: date | None = None,
) -> bool:
    """Sanity checks: rango absoluto y desviación vs el último valor de fecha cercana.

    La ventana de fechas evita descartar históricos legítimos durante el backfill,
    donde la tasa de hace meses sí puede diferir >50% de la actual.
    """
    if not (RATE_MIN <= quote.rate <= RATE_MAX):
        log.warning(
            "Tasa descartada fuera de rango: %s %s = %s", quote.source, quote.currency, quote.rate
        )
        return False
    if (
        last_rate
        and last_value_date
        and abs((quote.value_date - last_value_date).days) <= DEVIATION_WINDOW_DAYS
        and abs(quote.rate - last_rate) / last_rate > MAX_DEVIATION
    ):
        log.warning(
            "Tasa descartada por desviación >±50%% vs %s: %s %s = %s",
            last_rate,
            quote.source,
            quote.currency,
            quote.rate,
        )
        return False
    return True
