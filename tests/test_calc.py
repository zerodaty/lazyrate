"""Tests de la lógica pura de la calculadora y del parser de montos es-VE."""

from __future__ import annotations

import pytest

from lazyrate.calc import Leg, disparity_pct, to_bs, to_currency
from lazyrate.format import parse_amount


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1.234,56", 1234.56),  # punto=miles, coma=decimal
        ("1234,56", 1234.56),  # solo coma → decimal
        ("1.000", 1000.0),  # un punto + 3 dígitos → miles
        ("1.234.567", 1234567.0),  # varios puntos → miles
        ("1,5", 1.5),  # solo coma → decimal
        ("10.25", 10.25),  # un punto, no 3 dígitos → decimal
        ("1000", 1000.0),  # sin separadores
        ("$ 1.234,50", 1234.5),  # símbolos y espacios se descartan
        ("1.234,50 Bs", 1234.5),
        ("  42  ", 42.0),
        ("-1.000", -1000.0),  # negativo con miles
    ],
)
def test_parse_amount_es_ve(text, expected):
    assert parse_amount(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "1,2,3", ".", ",", "-", "  "])
def test_parse_amount_rejects_garbage(text):
    assert parse_amount(text) is None


def test_to_bs_and_to_currency_are_inverse():
    assert to_bs(100, 130.0) == pytest.approx(13000.0)
    assert to_currency(13000, 130.0) == pytest.approx(100.0)


def test_to_currency_guards_zero_rate():
    assert to_currency(500, 0) == 0.0


def test_disparity_pct_sign_and_zero_base():
    # B por encima de A → disparidad positiva
    assert disparity_pct(108.0, 130.0) == pytest.approx((130 - 108) / 108 * 100)
    # B por debajo de A → negativa
    assert disparity_pct(130.0, 108.0) == pytest.approx((108 - 130) / 130 * 100)
    # base 0 → None (sin división por cero)
    assert disparity_pct(0.0, 5.0) is None


def test_leg_is_frozen():
    leg = Leg("bcv", "USD", 108.5)
    assert (leg.source, leg.currency, leg.rate) == ("bcv", "USD", 108.5)
    with pytest.raises(Exception):
        leg.rate = 1  # type: ignore[misc]
