"""Pantalla modal de configuración: edita y guarda config.toml."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.validation import Integer
from textual.widgets import Button, Input, Label, Select, SelectionList, Switch

from lazyrate import config as config_mod
from lazyrate.config import BCV_CURRENCIES, Config

TRADE_TYPES = [("SELL (vender USDT)", "SELL"), ("BUY (comprar USDT)", "BUY")]
_VALID_TRADE_TYPES = {value for _, value in TRADE_TYPES}
_NUMERIC_INPUTS = ("#in-refresh", "#in-decimals", "#in-maxads")


class _AnyValue(dict):
    """Para validar plantillas de barra: cualquier placeholder resuelve a ''."""

    def __missing__(self, key: str) -> str:
        return ""


class ConfigScreen(ModalScreen[bool]):
    """Editor de la configuración; devuelve True al guardar, False al cancelar."""

    BINDINGS = [Binding("escape", "cancel", "Cancelar")]

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        cfg = self.cfg
        with Vertical(id="config-dialog"):
            yield Label("Configuración", id="config-title")
            with VerticalScroll(id="config-body"):
                yield Label("General", classes="cfg-section")
                with Horizontal(classes="cfg-row"):
                    yield Label("Refresco (minutos)")
                    yield Input(
                        value=str(cfg.general.refresh_minutes),
                        type="integer",
                        validators=[Integer(minimum=1, failure_description="Debe ser > 0")],
                        id="in-refresh",
                    )
                with Horizontal(classes="cfg-row"):
                    yield Label("Decimales (0–4)")
                    yield Input(
                        value=str(cfg.general.decimals),
                        type="integer",
                        validators=[
                            Integer(minimum=0, maximum=4, failure_description="Entre 0 y 4")
                        ],
                        id="in-decimals",
                    )

                yield Label("Barra", classes="cfg-section")
                with Horizontal(classes="cfg-row"):
                    yield Label("Formato de la barra")
                    yield Input(value=cfg.bar.format, id="in-barformat")
                with Horizontal(classes="cfg-row"):
                    yield Label("Marcar datos viejos")
                    yield Switch(value=cfg.bar.stale_mark, id="sw-stale")

                yield Label("BCV", classes="cfg-section")
                with Horizontal(classes="cfg-row"):
                    yield Label("Habilitado")
                    yield Switch(value=cfg.bcv.enabled, id="sw-bcv")
                with Horizontal(classes="cfg-row"):
                    yield Label("Monedas")
                    yield SelectionList[str](
                        *[(c, c, c in cfg.bcv.currencies) for c in BCV_CURRENCIES],
                        id="sel-currencies",
                    )

                yield Label("Binance P2P", classes="cfg-section")
                with Horizontal(classes="cfg-row"):
                    yield Label("Habilitado")
                    yield Switch(value=cfg.binance.enabled, id="sw-binance")
                with Horizontal(classes="cfg-row"):
                    yield Label("Solo comerciantes")
                    yield Switch(value=cfg.binance.merchant_only, id="sw-merchant")
                with Horizontal(classes="cfg-row"):
                    yield Label("Tipo de operación")
                    # Saneado: un TOML editado a mano con "buy"/"venta" crashearía el Select
                    trade_type = str(cfg.binance.trade_type).upper()
                    if trade_type not in _VALID_TRADE_TYPES:
                        trade_type = "SELL"
                    yield Select(
                        TRADE_TYPES,
                        value=trade_type,
                        allow_blank=False,
                        id="sel-trade",
                    )
                with Horizontal(classes="cfg-row"):
                    yield Label("Máx. anuncios (20–200)")
                    yield Input(
                        value=str(cfg.binance.max_ads),
                        type="integer",
                        validators=[
                            Integer(minimum=20, maximum=200, failure_description="Entre 20 y 200")
                        ],
                        id="in-maxads",
                    )
            with Horizontal(id="config-buttons"):
                yield Button("Guardar", variant="success", id="btn-save")
                yield Button("Cancelar", variant="default", id="btn-cancel")

    # ------------------------------------------------------------------ acciones

    def _inputs_valid(self) -> bool:
        ok = True
        for selector in _NUMERIC_INPUTS:
            field = self.query_one(selector, Input)
            result = field.validate(field.value)
            if result is not None and not result.is_valid:
                ok = False
        return ok

    @on(Button.Pressed, "#btn-save")
    def _on_save(self) -> None:
        if not self._inputs_valid():
            self.notify("Corrige los campos inválidos antes de guardar", severity="error")
            return
        bar_format = self.query_one("#in-barformat", Input).value
        try:
            bar_format.format_map(_AnyValue())
        except Exception:  # noqa: BLE001 — str.format lanza varios tipos según el error
            self.notify("Formato de barra inválido (revisa las llaves {})", severity="error")
            return
        bcv_enabled = self.query_one("#sw-bcv", Switch).value
        selected = set(self.query_one("#sel-currencies", SelectionList).selected)
        if bcv_enabled and not selected:
            self.notify(
                "Selecciona al menos una moneda BCV o deshabilita BCV", severity="error"
            )
            return
        cfg = self.cfg
        cfg.general.refresh_minutes = int(self.query_one("#in-refresh", Input).value)
        cfg.general.decimals = int(self.query_one("#in-decimals", Input).value)
        cfg.bar.format = bar_format
        cfg.bar.stale_mark = self.query_one("#sw-stale", Switch).value
        cfg.bcv.enabled = bcv_enabled
        cfg.bcv.currencies = [c for c in BCV_CURRENCIES if c in selected]
        cfg.binance.enabled = self.query_one("#sw-binance", Switch).value
        cfg.binance.merchant_only = self.query_one("#sw-merchant", Switch).value
        cfg.binance.trade_type = str(self.query_one("#sel-trade", Select).value)
        cfg.binance.max_ads = int(self.query_one("#in-maxads", Input).value)
        config_mod.save(cfg)
        self.notify("Configuración guardada")
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)
