"""Formato de números estilo es-VE (coma decimal, punto de miles), sin depender de locale."""


def format_rate(value: float, decimals: int = 2) -> str:
    text = f"{value:,.{decimals}f}"  # p.ej. 1,234.56
    return text.translate(str.maketrans(",.", ".,"))
