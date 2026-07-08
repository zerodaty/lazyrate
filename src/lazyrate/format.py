"""Formato de números estilo es-VE (coma decimal, punto de miles), sin depender de locale."""

from __future__ import annotations

import re

# Todo lo que no sea dígito, separador o signo se descarta antes de parsear
# (así "$ 1.234,50" o "1.234,50 Bs" se aceptan igual).
_NON_NUMERIC = re.compile(r"[^\d.,-]")
# Un único punto seguido de exactamente 3 dígitos hasta el final: "1.000" = miles, no 1.0
_DOT_THOUSANDS = re.compile(r"^-?\d{1,3}\.\d{3}$")


def format_rate(value: float, decimals: int = 2) -> str:
    text = f"{value:,.{decimals}f}"  # p.ej. 1,234.56
    return text.translate(str.maketrans(",.", ".,"))


def format_pct(value: float, decimals: int = 2) -> str:
    """Porcentaje con signo y coma decimal es-VE: '+0,21%'."""
    return f"{value:+.{decimals}f}".replace(".", ",") + "%"


def parse_amount(text: str) -> float | None:
    """Convierte un monto escrito en es-VE a float; ``None`` si no es parseable.

    Inverso de ``format_rate``. Convención es-VE: la coma es el separador decimal
    y el punto el de miles. Reglas:
      - coma y punto → punto=miles, coma=decimal ("1.234,56" → 1234.56)
      - solo coma    → decimal ("1234,56" → 1234.56)
      - solo puntos  → varios puntos, o uno con 3 dígitos finales, son miles
                       ("1.000" → 1000.0, "1.234.567" → 1234567.0); en otro caso
                       el punto es decimal ("10.25" → 10.25)
      - sin separadores → entero ("1000" → 1000.0)
    """
    cleaned = _NON_NUMERIC.sub("", text)
    if not cleaned:
        return None
    has_comma = "," in cleaned
    has_dot = "." in cleaned
    if has_comma and has_dot:
        normalized = cleaned.replace(".", "").replace(",", ".")
    elif has_comma:
        normalized = cleaned.replace(",", ".")
    elif has_dot and (cleaned.count(".") > 1 or _DOT_THOUSANDS.match(cleaned)):
        normalized = cleaned.replace(".", "")
    else:
        normalized = cleaned
    try:
        return float(normalized)
    except ValueError:
        return None
