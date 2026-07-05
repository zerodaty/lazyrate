"""Aplicación TUI estilo lazydocker: fuentes a la izquierda, gráfico y estadísticas."""

from __future__ import annotations

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Select, Sparkline, TabbedContent, TabPane
from textual.widgets.option_list import Option

from lazyrate import config as config_mod
from lazyrate import service, stats, store
from lazyrate.calc import disparity_pct
from lazyrate.format import format_rate
from lazyrate.tui.calculator_view import CalculatorView
from lazyrate.tui.widgets import (
    RateChart,
    Series,
    SourcesList,
    StatsPanel,
    format_pct,
    pair_label,
    source_label,
)

RANGE_LABELS = {7: "7d", 30: "30d", 90: "90d", 0: "todo"}
STATS_SPARK_POINTS = 30
CALC_TAB_ID = "tab-calc"


class LazyrateApp(App):
    """TUI de lazyrate: tasas BCV y Binance P2P con histórico y estadísticas."""

    TITLE = "lazyrate"
    CSS_PATH = "lazyrate.tcss"

    BINDINGS = [
        Binding("q", "quit", "Salir"),
        Binding("r", "refresh_data", "Actualizar"),
        Binding("c", "open_config", "Configuración"),
        Binding("equals_sign", "open_calculator", "Calculadora"),
        Binding("escape", "back_to_fuentes", "Volver", show=False),
        Binding("b", "toggle_compare", "Comparar"),
        Binding("7", "set_range(7)", "7d"),
        Binding("3", "set_range(30)", "30d"),
        Binding("9", "set_range(90)", "90d"),
        Binding("a", "set_range(0)", "Todo"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cfg = config_mod.load()
        self.pairs: list[tuple[str, str]] = []
        self.range_days: int = 30  # 0 = todo el histórico
        self.compare: bool = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with TabbedContent(initial="tab-fuentes", id="left-tabs"):
                with TabPane("Fuentes", id="tab-fuentes"):
                    yield SourcesList(id="sources")
                with TabPane("Calculadora", id=CALC_TAB_ID):
                    yield CalculatorView(self.cfg, id="calc-view")
            with Vertical(id="right"):
                yield RateChart(id="chart")
                with Vertical(id="stats-box"):
                    yield StatsPanel(id="stats")
                    yield Sparkline([], id="spark")
        yield Footer()

    def on_mount(self) -> None:
        self._main_widget("#stats-box", Vertical).border_title = "Estadísticas"
        self._reload_pairs()
        self._refresh_views()
        self._main_widget("#sources", SourcesList).focus()

    # ------------------------------------------------------------------ datos

    def _main_widget(self, selector: str, cls):
        """Resuelve widgets contra la pantalla principal, no la activa.

        Un refresh en hilo puede terminar con el modal de configuración abierto;
        query_one sobre la app buscaría en el modal y lanzaría NoMatches.
        """
        return self.screen_stack[0].query_one(selector, cls)

    @property
    def active_pair(self) -> tuple[str, str] | None:
        index = self._main_widget("#sources", SourcesList).highlighted
        if index is None or not (0 <= index < len(self.pairs)):
            return None
        return self.pairs[index]

    def _reload_pairs(self) -> None:
        """Une los pares habilitados por configuración con los que tienen datos."""
        self.pairs = service.available_pairs(self.cfg)
        sources = self._main_widget("#sources", SourcesList)
        previous = sources.highlighted if sources.highlighted is not None else 0
        sources.clear_options()
        sources.add_options(
            Option(pair_label(src, cur), id=f"{src}:{cur}") for src, cur in self.pairs
        )
        if self.pairs:
            sources.highlighted = min(previous, len(self.pairs) - 1)

    def _reload_calc(self) -> None:
        """Re-sincroniza el panel de la calculadora tras un refresco o cambio de config."""
        try:
            calc = self._main_widget("#calc-view", CalculatorView)
        except Exception:  # noqa: BLE001 — aún no montado
            return
        calc.reload(self.cfg)

    def _calc_tab_active(self) -> bool:
        return self._main_widget("#left-tabs", TabbedContent).active == CALC_TAB_ID

    def _focus_calc_input(self) -> None:
        calc = self._main_widget("#calc-view", CalculatorView)
        field = calc.query("#calc-amount")
        if field:
            field.first().focus()

    def _series(self, source: str, currency: str) -> Series:
        return store.daily_series(source, currency, days=self.range_days or None)

    # ------------------------------------------------------------------ vistas

    def _refresh_views(self) -> None:
        """Refresca el panel derecho según la pestaña activa (fuente vs comparación A/B)."""
        if self._calc_tab_active():
            self._update_comparison()
        else:
            self._main_widget("#stats-box", Vertical).border_title = "Estadísticas"
            self._update_chart()
            self._update_stats()

    def _update_chart(self) -> None:
        chart = self._main_widget("#chart", RateChart)
        range_label = RANGE_LABELS[self.range_days]
        if self.compare:
            series_list = [
                ("BCV USD", self._series("bcv", "USD")),
                ("Binance USDT", self._series("binance_p2p", "USDT")),
            ]
            title = f"Evolución ({range_label}) — BCV USD vs Binance USDT"
        else:
            pair = self.active_pair
            if pair is None:
                chart.update_chart([], f"Evolución ({range_label})")
                return
            source, currency = pair
            label = f"{source_label(source)} {currency}"
            series_list = [(label, self._series(source, currency))]
            title = f"Evolución ({range_label}) — {label}"
        chart.update_chart(series_list, title)

    def _update_stats(self) -> None:
        panel = self._main_widget("#stats", StatsPanel)
        spark = self._main_widget("#spark", Sparkline)
        pair = self.active_pair
        if pair is None:
            panel.update_stats([("Sin datos", "presiona r para obtener")])
            spark.data = []
            return
        source, currency = pair
        series = store.daily_series(source, currency)
        rows = self._stats_rows(series)
        gap_row = self._gap_row()
        if gap_row is not None:
            rows.append(gap_row)
        panel.update_stats(rows)
        spark.data = [rate for _, rate in series[-STATS_SPARK_POINTS:]]

    def _stats_rows(self, series: Series) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        head = stats.current(series)
        rows.append(
            ("Actual", f"{format_rate(head[1], 4)} Bs ({head[0]:%d/%m/%Y})" if head else "—")
        )
        change = stats.day_change_pct(series)
        rows.append(("Var. día", format_pct(change) if change is not None else "—"))
        for label, days in (("Prom 7d", 7), ("Prom 30d", 30)):
            mean = stats.mean_last(series, days)
            rows.append((label, f"{format_rate(mean, 4)} Bs" if mean is not None else "—"))
        extremes = stats.min_max_last(series, 30)
        if extremes:
            (low_day, low), (high_day, high) = extremes
            rows.append(("Mín 30d", f"{format_rate(low, 4)} Bs ({low_day:%d/%m/%Y})"))
            rows.append(("Máx 30d", f"{format_rate(high, 4)} Bs ({high_day:%d/%m/%Y})"))
        else:
            rows.append(("Mín 30d", "—"))
            rows.append(("Máx 30d", "—"))
        movement = stats.trend(series, points=7)
        rows.append(
            ("Tendencia 7d", f"{movement[1]} ({format_pct(movement[0])}/día)" if movement else "—")
        )
        return rows

    def _gap_row(self) -> tuple[str, str] | None:
        """Brecha BCV↔P2P, solo si existen ambas series."""
        bcv_series = store.daily_series("bcv", "USD")
        p2p_series = store.daily_series("binance_p2p", "USDT")
        if not bcv_series or not p2p_series:
            return None
        gap = stats.gap_pct(bcv_series, p2p_series)
        return ("Brecha BCV↔P2P", format_pct(gap) if gap is not None else "—")

    # ----------------------------------------------------- vista de comparación

    def _update_comparison(self) -> None:
        """Panel derecho en la pestaña Calculadora: gráfica A vs B y su brecha."""
        chart = self._main_widget("#chart", RateChart)
        panel = self._main_widget("#stats", StatsPanel)
        spark = self._main_widget("#spark", Sparkline)
        self._main_widget("#stats-box", Vertical).border_title = "Comparación"
        range_label = RANGE_LABELS[self.range_days]

        legs = self._main_widget("#calc-view", CalculatorView).current_legs()
        if legs is None:
            chart.update_chart([], f"Comparación ({range_label})")
            panel.update_stats([("Sin datos", "presiona r para obtener")])
            spark.data = []
            return
        (src_a, cur_a), (src_b, cur_b) = legs
        label_a = f"{source_label(src_a)} {cur_a}"
        label_b = f"{source_label(src_b)} {cur_b}"
        series_a = self._series(src_a, cur_a)
        series_b = self._series(src_b, cur_b)
        chart.update_chart(
            [(label_a, series_a), (label_b, series_b)],
            f"Comparación ({range_label}) — {label_a} vs {label_b}",
        )
        panel.update_stats(self._comparison_rows(label_a, series_a, label_b, series_b))
        spark.data = [rate for _, rate in series_b[-STATS_SPARK_POINTS:]]

    def _comparison_rows(
        self, label_a: str, series_a: Series, label_b: str, series_b: Series
    ) -> list[tuple[str, str]]:
        head_a = stats.current(series_a)
        head_b = stats.current(series_b)
        rows: list[tuple[str, str]] = [
            (f"A · {label_a}", f"{format_rate(head_a[1], 4)} Bs" if head_a else "—"),
            (f"B · {label_b}", f"{format_rate(head_b[1], 4)} Bs" if head_b else "—"),
        ]
        if head_a and head_b:
            gap = disparity_pct(head_a[1], head_b[1])
            rows.append(("Disparidad B vs A", format_pct(gap) if gap is not None else "—"))
        mean_a = stats.mean_last(series_a, 30)
        mean_b = stats.mean_last(series_b, 30)
        rows.append(("Prom 30d A", f"{format_rate(mean_a, 4)} Bs" if mean_a is not None else "—"))
        rows.append(("Prom 30d B", f"{format_rate(mean_b, 4)} Bs" if mean_b is not None else "—"))
        trend_a = stats.trend(series_a, points=7)
        trend_b = stats.trend(series_b, points=7)
        rows.append(("Tendencia A", trend_a[1] if trend_a else "—"))
        rows.append(("Tendencia B", trend_b[1] if trend_b else "—"))
        return rows

    # ------------------------------------------------------------------ eventos

    @on(SourcesList.OptionHighlighted, "#sources")
    @on(SourcesList.OptionSelected, "#sources")
    def _on_source_changed(self) -> None:
        if not self._calc_tab_active():
            self._refresh_views()

    @on(TabbedContent.TabActivated, "#left-tabs")
    def _on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane is not None and event.pane.id == CALC_TAB_ID:
            self._update_comparison()
        else:
            self._main_widget("#stats-box", Vertical).border_title = "Estadísticas"
            self._update_chart()
            self._update_stats()

    @on(Select.Changed)
    def _on_calc_leg_changed(self) -> None:
        # Cambiar Tasa A/B en la calculadora re-grafica la comparación del panel derecho
        if self._calc_tab_active():
            self._update_comparison()

    # ------------------------------------------------------------------ acciones

    def action_set_range(self, days: int) -> None:
        self.range_days = days
        self._refresh_views()

    def action_toggle_compare(self) -> None:
        self.compare = not self.compare
        self._refresh_views()

    def action_open_config(self) -> None:
        from lazyrate.tui.config_screen import ConfigScreen

        def _on_close(saved: bool | None) -> None:
            if saved:
                self.cfg = config_mod.load()
                self._reload_pairs()
                self._reload_calc()
                self._refresh_views()

        self.push_screen(ConfigScreen(self.cfg), _on_close)

    def action_open_calculator(self) -> None:
        """Alterna entre las pestañas Calculadora y Fuentes (atajo de la tecla '=')."""
        tabs = self._main_widget("#left-tabs", TabbedContent)
        # Textual no oculta un pane cuyo hijo tiene el foco: hay que soltarlo antes.
        self.set_focus(None)
        if tabs.active == CALC_TAB_ID:
            tabs.active = "tab-fuentes"
            self._main_widget("#sources", SourcesList).focus()
        else:
            tabs.active = CALC_TAB_ID
            self._focus_calc_input()

    def action_back_to_fuentes(self) -> None:
        """Vuelve a la pestaña Fuentes (Esc); útil mientras se escribe el monto."""
        tabs = self._main_widget("#left-tabs", TabbedContent)
        if tabs.active == CALC_TAB_ID:
            self.set_focus(None)
            tabs.active = "tab-fuentes"
            self._main_widget("#sources", SourcesList).focus()

    def action_refresh_data(self) -> None:
        self.notify("Actualizando tasas…", timeout=3)
        self._do_refresh()

    @work(thread=True, exclusive=True)
    def _do_refresh(self) -> None:
        """Consulta proveedores en un hilo; si no hay histórico BCV, hace backfill."""
        got_data = False
        try:
            from lazyrate.providers import bcv
            from lazyrate.providers.base import validate_quote

            got_data = bool(service.fetch_and_store(self.cfg))
            no_bcv_rows = not any(source == "bcv" for source, _ in store.sources_with_data())
            if self.cfg.bcv.enabled and self.cfg.bcv.currencies and no_bcv_rows:
                quotes = [q for q in bcv.backfill(self.cfg) if validate_quote(q)]
                got_data = store.insert_quotes(quotes) > 0 or got_data
        except Exception as exc:  # noqa: BLE001 — la TUI no debe caerse por fallos de red
            self.app.call_from_thread(
                self.notify, f"Error al actualizar: {exc}", severity="error", timeout=6
            )
            return
        self.app.call_from_thread(self._after_refresh, got_data)

    def _after_refresh(self, got_data: bool) -> None:
        self._reload_pairs()
        self._reload_calc()
        self._refresh_views()
        if got_data:
            self.notify("Tasas actualizadas", timeout=3)
        else:
            self.notify(
                "No se obtuvieron datos nuevos (¿sin conexión?)", severity="warning", timeout=5
            )
