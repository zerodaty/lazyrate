"""Tests de lazyrate.stats: funciones puras sobre series diarias [(fecha, tasa)]."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from lazyrate import stats

D0 = date(2026, 6, 1)


def _series(values: list[float], start: date = D0) -> stats.Series:
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


# --- trend ---


def test_trend_rising():
    result = stats.trend(_series([100, 102, 104, 106, 108, 110, 112]))
    assert result is not None
    slope_pct, label = result
    assert slope_pct > 0
    assert label == "subiendo ↑"


def test_trend_falling():
    result = stats.trend(_series([112, 110, 108, 106, 104, 102, 100]))
    assert result is not None
    slope_pct, label = result
    assert slope_pct < 0
    assert label == "bajando ↓"


def test_trend_flat():
    result = stats.trend(_series([100.0, 100.0, 100.01, 100.0, 100.0]))
    assert result is not None
    slope_pct, label = result
    assert abs(slope_pct) < stats.TREND_FLAT_THRESHOLD
    assert label == "estable →"


def test_trend_needs_two_points():
    assert stats.trend([]) is None
    assert stats.trend(_series([100.0])) is None


def test_trend_uses_only_last_points():
    # Cae fuerte al principio pero sube en los últimos 3 puntos considerados
    series = _series([500, 400, 300, 100, 102, 104])
    result = stats.trend(series, points=3)
    assert result is not None
    assert result[1] == "subiendo ↑"


# --- day_change_pct ---


def test_day_change_pct():
    assert stats.day_change_pct(_series([100.0, 110.0])) == pytest.approx(10.0)
    assert stats.day_change_pct(_series([110.0, 99.0])) == pytest.approx(-10.0)


def test_day_change_pct_needs_two_points():
    assert stats.day_change_pct([]) is None
    assert stats.day_change_pct(_series([100.0])) is None


def test_day_change_pct_zero_prev():
    assert stats.day_change_pct(_series([0.0, 100.0])) is None


# --- window / mean_last (con huecos de fechas) ---


def test_window_with_date_gaps():
    # Huecos: datos en los días 0, 4 y 9; el último dato ancla la ventana
    series = [(D0, 100.0), (D0 + timedelta(days=4), 200.0), (D0 + timedelta(days=9), 300.0)]
    points = stats.window(series, days=7)
    # Ventana de 7 días calendario desde el día 9: incluye días 3..9 → días 4 y 9
    assert points == [(D0 + timedelta(days=4), 200.0), (D0 + timedelta(days=9), 300.0)]


def test_window_empty_series():
    assert stats.window([], days=7) == []


def test_mean_last_with_date_gaps():
    series = [(D0, 100.0), (D0 + timedelta(days=4), 200.0), (D0 + timedelta(days=9), 300.0)]
    assert stats.mean_last(series, days=7) == pytest.approx(250.0)
    assert stats.mean_last(series, days=30) == pytest.approx(200.0)
    assert stats.mean_last([], days=7) is None


# --- min_max_last ---


def test_min_max_last_returns_correct_dates():
    series = [
        (D0, 105.0),
        (D0 + timedelta(days=1), 101.0),
        (D0 + timedelta(days=2), 110.0),
        (D0 + timedelta(days=3), 107.0),
    ]
    result = stats.min_max_last(series, days=30)
    assert result is not None
    lowest, highest = result
    assert lowest == (D0 + timedelta(days=1), 101.0)
    assert highest == (D0 + timedelta(days=2), 110.0)


def test_min_max_last_respects_window():
    # El mínimo global queda fuera de la ventana de 2 días
    series = [(D0, 50.0), (D0 + timedelta(days=5), 100.0), (D0 + timedelta(days=6), 120.0)]
    result = stats.min_max_last(series, days=2)
    assert result is not None
    lowest, highest = result
    assert lowest == (D0 + timedelta(days=5), 100.0)
    assert highest == (D0 + timedelta(days=6), 120.0)


def test_min_max_last_empty():
    assert stats.min_max_last([], days=7) is None


# --- gap_pct ---


def test_gap_pct_uses_most_recent_common_day():
    bcv = [(D0, 100.0), (D0 + timedelta(days=1), 100.0), (D0 + timedelta(days=2), 110.0)]
    # P2P tiene dato el día 2 (común más reciente) y el día 3 (sin BCV)
    p2p = [(D0 + timedelta(days=2), 132.0), (D0 + timedelta(days=3), 999.0)]
    assert stats.gap_pct(bcv, p2p) == pytest.approx((132.0 - 110.0) / 110.0 * 100)


def test_gap_pct_no_common_day():
    bcv = [(D0, 100.0)]
    p2p = [(D0 + timedelta(days=1), 130.0)]
    assert stats.gap_pct(bcv, p2p) is None
    assert stats.gap_pct([], []) is None


# --- current ---


def test_current():
    assert stats.current([]) is None
    assert stats.current(_series([100.0, 105.0])) == (D0 + timedelta(days=1), 105.0)
