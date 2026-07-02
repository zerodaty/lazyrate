"""Estadísticas puras sobre series diarias [(fecha, tasa)]. Solo stdlib."""

from __future__ import annotations

import statistics
from datetime import date, timedelta

Series = list[tuple[date, float]]

TREND_FLAT_THRESHOLD = 0.05  # %/día por debajo del cual la tendencia se considera estable


def current(series: Series) -> tuple[date, float] | None:
    return series[-1] if series else None


def day_change_pct(series: Series) -> float | None:
    """Variación % del último dato vs el dato anterior (último día con dato, no calendario)."""
    if len(series) < 2:
        return None
    (_, prev), (_, last) = series[-2], series[-1]
    if prev == 0:
        return None
    return (last - prev) / prev * 100


def window(series: Series, days: int) -> Series:
    """Puntos dentro de los últimos `days` días calendario, relativo al último dato."""
    if not series:
        return []
    start = series[-1][0] - timedelta(days=days - 1)
    return [p for p in series if p[0] >= start]


def mean_last(series: Series, days: int) -> float | None:
    points = window(series, days)
    return statistics.fmean(r for _, r in points) if points else None


def min_max_last(
    series: Series, days: int
) -> tuple[tuple[date, float], tuple[date, float]] | None:
    points = window(series, days)
    if not points:
        return None
    lowest = min(points, key=lambda p: p[1])
    highest = max(points, key=lambda p: p[1])
    return lowest, highest


def trend(series: Series, points: int = 7) -> tuple[float, str] | None:
    """Pendiente de regresión lineal sobre los últimos `points` datos, en %/día."""
    values = [r for _, r in series[-points:]]
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    slope = statistics.linear_regression(range(len(values)), values).slope
    slope_pct = slope / mean * 100
    if abs(slope_pct) < TREND_FLAT_THRESHOLD:
        label = "estable →"
    elif slope_pct > 0:
        label = "subiendo ↑"
    else:
        label = "bajando ↓"
    return slope_pct, label


def gap_pct(bcv_series: Series, p2p_series: Series) -> float | None:
    """Brecha BCV↔P2P en %, sobre el día común más reciente de ambas series."""
    bcv_by_day = dict(bcv_series)
    for day, p2p_rate in reversed(p2p_series):
        bcv_rate = bcv_by_day.get(day)
        if bcv_rate:
            return (p2p_rate - bcv_rate) / bcv_rate * 100
    return None
