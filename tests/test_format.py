"""Tests de lazyrate.format: formato numérico es-VE (coma decimal, punto de miles)."""

from __future__ import annotations

from lazyrate.format import format_rate


def test_thousands_and_decimal_separator():
    assert format_rate(1234.5678, 2) == "1.234,57"


def test_padding_of_decimals():
    assert format_rate(0.5, 4) == "0,5000"


def test_default_two_decimals():
    assert format_rate(108.5) == "108,50"


def test_millions():
    assert format_rate(1234567.891, 2) == "1.234.567,89"


def test_zero_decimals():
    assert format_rate(1234.9, 0) == "1.235"
