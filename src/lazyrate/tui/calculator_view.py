"""Panel de la calculadora, en la pestaña "Calculadora" de la columna izquierda.

Convierte un monto comparando dos tasas en ambos sentidos (divisa→Bs y Bs→divisa)
y muestra el % de disparidad. No consulta la red: usa solo las tasas guardadas.
Recuerda la última selección en la sección ``[calc]`` del config.toml. El panel
derecho grafica en paralelo las dos tasas elegidas (lo hace ``LazyrateApp``).
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.validation import Function
from textual.widgets import Button, Input, Label, Select

from lazyrate import config as config_mod
from lazyrate import service
from lazyrate.calc import disparity_pct, to_bs, to_currency
from lazyrate.config import Config
from lazyrate.format import format_rate, parse_amount
from lazyrate.tui.widgets import StatsPanel, format_pct, pair_label

_DIRECTIONS = ("to_bs", "to_currency")
_DIRECTION_OPTIONS = [("Divisa → Bs", "to_bs"), ("Bs → Divisa", "to_currency")]
_EMPTY = "—"


def _pair_value(source: str, currency: str) -> str:
    return f"{source}:{currency}"


class CalculatorView(VerticalScroll):
    """Calculadora de conversión, apilada para la columna izquierda angosta."""

    def __init__(self, cfg: Config, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cfg = cfg
        self.pairs = service.available_pairs(cfg)
        self._ready = False
        self._last_copy: str | None = None
        self._initial = self._calc_snapshot()

    def _calc_snapshot(self) -> tuple:
        c = self.cfg.calc
        return (c.source_a, c.currency_a, c.source_b, c.currency_b, c.direction)

    # ------------------------------------------------------------------ layout

    def _options(self) -> list[tuple[str, str]]:
        return [(pair_label(src, cur), _pair_value(src, cur)) for src, cur in self.pairs]

    def _initial_value(self, source: str, currency: str) -> str:
        """Valor inicial de un Select: el guardado si sigue disponible, si no el primero."""
        wanted = _pair_value(source, currency)
        available = {_pair_value(src, cur) for src, cur in self.pairs}
        if wanted in available:
            return wanted
        return _pair_value(*self.pairs[0])

    def compose(self) -> ComposeResult:
        if not self.pairs:
            yield Label(
                "Sin datos todavía.\nPulsa r para obtener las tasas.", id="calc-empty"
            )
            return
        options = self._options()
        direction = self.cfg.calc.direction if self.cfg.calc.direction in _DIRECTIONS else "to_bs"
        yield Label("Dirección", classes="calc-label")
        yield Select(_DIRECTION_OPTIONS, value=direction, allow_blank=False, id="calc-direction")
        yield Label("Monto (divisa)", id="calc-amount-label", classes="calc-label")
        yield Input(
            placeholder="0,00",
            type="text",
            restrict=r"[0-9.,\-]*",  # solo dígitos y separadores es-VE
            validators=[Function(self._amount_ok, "Monto inválido")],
            id="calc-amount",
        )
        yield Label("coma decimal · ej. 1.234,56", id="calc-hint")
        yield Label("Tasa A", classes="calc-label")
        yield Select(
            options,
            value=self._initial_value(self.cfg.calc.source_a, self.cfg.calc.currency_a),
            allow_blank=False,
            id="calc-leg-a",
        )
        yield Label("Tasa B", classes="calc-label")
        yield Select(
            options,
            value=self._initial_value(self.cfg.calc.source_b, self.cfg.calc.currency_b),
            allow_blank=False,
            id="calc-leg-b",
        )
        yield Label("Resultado", classes="cfg-section")
        yield StatsPanel(id="calc-result")
        yield Button("Copiar resultado", variant="default", id="btn-copy")
        yield Label("Esc o = : volver a Fuentes", id="calc-back-hint")

    def on_mount(self) -> None:
        self._ready = True
        self.call_after_refresh(self._recompute)

    def reload(self, cfg: Config) -> None:
        """Re-sincroniza con la config/datos actuales tras un refresco o cambio de config."""
        self.cfg = cfg
        new_pairs = service.available_pairs(cfg)
        if new_pairs == self.pairs:
            self._recompute()  # las tasas pueden haber cambiado; conserva lo escrito
            return
        self.pairs = new_pairs
        self.recompose()
        self.call_after_refresh(self._recompute)

    # ------------------------------------------------------------------ datos

    def current_legs(self) -> tuple[tuple[str, str], tuple[str, str]] | None:
        """Pares (fuente, moneda) elegidos en Tasa A y Tasa B; None si aún no hay datos."""
        if not self.pairs:
            return None
        try:
            return self._selected_pair("#calc-leg-a"), self._selected_pair("#calc-leg-b")
        except Exception:  # noqa: BLE001 — selects aún no montados
            return None

    # ------------------------------------------------------------------ cálculo

    @staticmethod
    def _amount_ok(value: str) -> bool:
        return not value.strip() or parse_amount(value) is not None

    def _direction(self) -> str:
        value = self.query_one("#calc-direction", Select).value
        return str(value) if value in _DIRECTIONS else "to_bs"

    def _selected_pair(self, selector: str) -> tuple[str, str]:
        value = self.query_one(selector, Select).value
        source, currency = str(value).split(":", 1)
        return source, currency

    def _result_row(
        self, source: str, currency: str, amount: float | None, direction: str
    ) -> tuple[str, str, float | None]:
        """Devuelve (etiqueta, texto, valor_numérico) para una leg."""
        label = pair_label(source, currency)
        row = service.latest_rate(source, currency)
        if row is None:
            return label, f"{_EMPTY} sin datos", None
        if amount is None:
            return label, _EMPTY, None
        decimals = self.cfg.general.decimals
        if direction == "to_currency":
            value = to_currency(amount, row.rate)
            return label, f"{format_rate(value, decimals)} {currency}", value
        value = to_bs(amount, row.rate)
        return label, f"{format_rate(value, decimals)} Bs", value

    def _recompute(self) -> None:
        if not self._ready or not self.pairs:
            return
        direction = self._direction()
        self.query_one("#calc-amount-label", Label).update(
            "Monto (Bs)" if direction == "to_currency" else "Monto (divisa)"
        )
        amount = parse_amount(self.query_one("#calc-amount", Input).value)

        src_a, cur_a = self._selected_pair("#calc-leg-a")
        src_b, cur_b = self._selected_pair("#calc-leg-b")
        label_a, text_a, num_a = self._result_row(src_a, cur_a, amount, direction)
        label_b, text_b, num_b = self._result_row(src_b, cur_b, amount, direction)

        rows = [(label_a, text_a), (label_b, text_b)]
        if num_a is not None and num_b is not None:
            gap = disparity_pct(num_a, num_b)
            rows.append(("Disparidad (B vs A)", format_pct(gap) if gap is not None else _EMPTY))
        self._last_copy = text_b if num_b is not None else None
        self.query_one("#calc-result", StatsPanel).update_stats(rows)

        # Refleja la selección en memoria para recordarla al salir
        self.cfg.calc.source_a, self.cfg.calc.currency_a = src_a, cur_a
        self.cfg.calc.source_b, self.cfg.calc.currency_b = src_b, cur_b
        self.cfg.calc.direction = direction

    # ------------------------------------------------------------------ eventos

    @on(Input.Changed, "#calc-amount")
    @on(Select.Changed)
    def _on_change(self) -> None:
        self._recompute()

    @on(Button.Pressed, "#btn-copy")
    def _on_copy(self) -> None:
        if self._last_copy:
            self.app.copy_to_clipboard(self._last_copy)
            self.notify(f"Copiado: {self._last_copy}", timeout=3)

    def on_unmount(self) -> None:
        if self.pairs and self._calc_snapshot() != self._initial:
            try:
                config_mod.save(self.cfg)
            except OSError:
                pass
