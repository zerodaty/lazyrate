"""Proveedor Binance P2P: promedio ponderado de anuncios USDT/VES con filtro IQR."""

from __future__ import annotations

import json
import logging
import statistics
import urllib.request
from typing import TYPE_CHECKING

from lazyrate.providers.base import (
    HTTP_TIMEOUT,
    MAX_RESPONSE_BYTES,
    Quote,
    now_utc,
    today_caracas,
)

if TYPE_CHECKING:
    from lazyrate.config import Config

log = logging.getLogger(__name__)

SEARCH_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
PAGE_SIZE = 20
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def build_payload(cfg: "Config", page: int) -> dict:
    """Cuerpo JSON de la búsqueda de anuncios para una página dada."""
    return {
        "asset": cfg.binance.asset,
        "fiat": "VES",
        "tradeType": cfg.binance.trade_type,
        "rows": PAGE_SIZE,
        "page": page,
        "publisherType": "merchant" if cfg.binance.merchant_only else None,
    }


def _fetch_page(payload: dict) -> dict:
    """POST al endpoint de búsqueda; devuelve el JSON decodificado."""
    request = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        raw = response.read(MAX_RESPONSE_BYTES)
    return json.loads(raw)


def _parse_offers(ads: list) -> list[tuple[float, float]]:
    """Extrae (precio, cantidad) de cada anuncio; ignora anuncios malformados."""
    offers: list[tuple[float, float]] = []
    for ad in ads:
        try:
            adv = ad["adv"]
            price = float(adv["price"])
            quantity = float(adv["tradableQuantity"])
        except (KeyError, TypeError, ValueError):
            log.debug("Anuncio Binance P2P ignorado por datos inválidos: %r", ad)
            continue
        if price > 0 and quantity > 0:
            offers.append((price, quantity))
    return offers


def iqr_filter(prices: list[float]) -> list[float]:
    """Descarta precios fuera de [q1 - 1.5*iqr, q3 + 1.5*iqr].

    Con menos de 4 precios no filtra; si el filtro vaciara la lista, devuelve la original.
    """
    n = len(prices)
    if n < 4:
        return prices
    ordered = sorted(prices)
    # Cuartiles interpolados: con índices nearest-rank y n pequeño (p.ej. 4),
    # q3 sería el propio máximo y un outlier alto jamás se filtraría.
    quartiles = statistics.quantiles(ordered, n=4, method="inclusive")
    q1, q3 = quartiles[0], quartiles[2]
    iqr = q3 - q1
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    kept = [p for p in prices if low <= p <= high]
    return kept if kept else prices


def weighted_average(offers: list[tuple[float, float]], accepted_prices: set[float]) -> float:
    """Promedio ponderado por cantidad de las ofertas con precio aceptado.

    Si la cantidad total es 0, cae a la media simple de los precios aceptados.
    """
    weighted_sum = 0.0
    quantity_sum = 0.0
    for price, quantity in offers:
        if price in accepted_prices:
            weighted_sum += price * quantity
            quantity_sum += quantity
    if quantity_sum == 0:
        return statistics.fmean(accepted_prices)
    return weighted_sum / quantity_sum


class BinanceP2PProvider:
    name = "binance_p2p"

    def fetch(self, cfg: "Config") -> list[Quote]:
        max_ads = cfg.binance.max_ads
        # Tope holgado de páginas: sin él, páginas llenas de anuncios inválidos
        # (deriva de esquema, respuesta hostil) harían un bucle sin fin.
        max_pages = 2 * -(-max_ads // PAGE_SIZE)
        offers: list[tuple[float, float]] = []
        page = 1
        while len(offers) < max_ads and page <= max_pages:
            response = _fetch_page(build_payload(cfg, page))
            ads = response.get("data") or []
            offers.extend(_parse_offers(ads))
            if len(ads) < PAGE_SIZE:
                break
            page += 1
        if page > max_pages and len(offers) < max_ads:
            log.warning(
                "Binance P2P: tope de %d páginas alcanzado con solo %d ofertas válidas",
                max_pages,
                len(offers),
            )
        offers = offers[:max_ads]
        if not offers:
            raise RuntimeError("Binance P2P no devolvió anuncios válidos para calcular la tasa")

        prices = [price for price, _ in offers]
        accepted = set(iqr_filter(prices))
        average = weighted_average(offers, accepted)
        ads_used = sum(1 for price, _ in offers if price in accepted)
        return [
            Quote(
                source=self.name,
                currency=cfg.binance.asset,
                rate=round(average, 4),
                fetched_at=now_utc(),
                value_date=today_caracas(),
                meta={"ads_used": ads_used, "ads_total": len(offers)},
            )
        ]
