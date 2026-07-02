"""Widgets de la TUI: lista de fuentes, gráfico de evolución y panel de estadísticas."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from rich.align import Align
from rich.table import Table
from rich.text import Text
from textual.binding import Binding
from textual.widgets import OptionList, Static
from textual_plotext import PlotextPlot

if TYPE_CHECKING:
    from textual.app import RenderResult

Series = list[tuple[date, float]]

SOURCE_LABELS = {"bcv": "BCV", "binance_p2p": "Binance P2P"}
EMPTY_MESSAGE = "Sin datos — presiona r para obtener"


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def pair_label(source: str, currency: str) -> str:
    """Etiqueta para la lista de fuentes: 'BCV · USD', 'Binance P2P · USDT'."""
    return f"{source_label(source)} · {currency}"


def format_pct(value: float, decimals: int = 2) -> str:
    """Porcentaje con signo y coma decimal es-VE: '+0,21%'."""
    return f"{value:+.{decimals}f}".replace(".", ",") + "%"


class SourcesList(OptionList):
    """Lista de pares fuente·moneda; j/k funcionan además de las flechas."""

    BINDINGS = [
        Binding("j", "cursor_down", "Bajar", show=False),
        Binding("k", "cursor_up", "Subir", show=False),
    ]


class RateChart(PlotextPlot):
    """Gráfico de series diarias con plotext: línea braille y fechas en el eje X."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._series: list[tuple[str, Series]] = []

    def update_chart(self, series_by_label: list[tuple[str, Series]], title: str) -> None:
        """Redibuja el gráfico; con varias series muestra leyenda (modo comparación)."""
        self._series = [(label, points) for label, points in series_by_label if points]
        self.border_title = title
        plt = self.plt
        plt.clear_figure()
        if self._series:
            plt.date_form("d/m/Y")
            show_legend = len(self._series) > 1
            for label, points in self._series:
                days = [day.strftime("%d/%m/%Y") for day, _ in points]
                rates = [rate for _, rate in points]
                plt.plot(days, rates, marker="braille", label=label if show_legend else None)
        self.refresh()

    def render(self) -> "RenderResult":
        if not self._series:
            return Align.center(Text(EMPTY_MESSAGE, style="dim italic"), vertical="middle")
        return super().render()


class StatsPanel(Static):
    """Tabla Rich con las estadísticas de la serie activa."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.plain_text: str = ""

    def update_stats(self, rows: list[tuple[str, str]]) -> None:
        table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
        table.add_column("métrica", style="bold", no_wrap=True)
        table.add_column("valor")
        for name, value in rows:
            table.add_row(name, value)
        self.plain_text = "\n".join(f"{name}: {value}" for name, value in rows)
        self.update(table)
