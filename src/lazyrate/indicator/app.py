"""Daemon del indicador de GNOME: label con las tasas, menú y ciclo de refresco."""

from __future__ import annotations

import fcntl
import logging
import logging.handlers
import signal
import sys
import threading
from datetime import date
from importlib.resources import files
from typing import IO

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
except (ImportError, ValueError):
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndicator  # noqa: E402

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from lazyrate import config as config_mod  # noqa: E402
from lazyrate import service, store  # noqa: E402
from lazyrate.cli import tui_command  # noqa: E402
from lazyrate.format import format_rate  # noqa: E402
from lazyrate.providers.base import now_utc, today_caracas, validate_quote  # noqa: E402

log = logging.getLogger(__name__)

INDICATOR_ID = "lazyrate"
ICON_NAME = "lazyrate"
BCV_MAX_AGE_MINUTES = 60  # re-consultar BCV si el último fetch tiene más de 1 hora


def _setup_logging() -> None:
    log_dir = config_mod.state_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "indicator.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    stream_handler = logging.StreamHandler()  # stderr
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])


def _acquire_single_instance_lock() -> IO[str] | None:
    """flock exclusivo no bloqueante sobre state_dir()/indicator.lock; None si ya hay otro."""
    lock_path = config_mod.state_dir() / "indicator.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


class IndicatorApp:
    """Estado del indicador: label, menú, timer de refresco y monitor de configuración."""

    def __init__(self, cfg: config_mod.Config) -> None:
        self.cfg = cfg
        self._fetch_busy = threading.Lock()
        self._last_purge_day: date | None = None
        self._timeout_id: int = 0

        self.indicator = AppIndicator.Indicator.new(
            INDICATOR_ID, ICON_NAME, AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        icon_dir = str(files("lazyrate") / "data")
        self.indicator.set_icon_theme_path(icon_dir)
        self.indicator.set_icon(ICON_NAME)
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        self.refresh_ui()  # pinta de inmediato lo que haya en la base de datos
        self._arm_timer()
        self._watch_config()
        self.start_fetch(first_run=True)

    # ------------------------------------------------------------------ timer

    def _arm_timer(self) -> None:
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
        seconds = max(60, self.cfg.general.refresh_minutes * 60)
        self._timeout_id = GLib.timeout_add_seconds(seconds, self._on_tick)

    def _on_tick(self) -> bool:
        self.start_fetch()
        return GLib.SOURCE_CONTINUE

    # ------------------------------------------------------------------ fetch (hilo)

    def start_fetch(self, first_run: bool = False) -> None:
        threading.Thread(
            target=self._fetch_worker, args=(first_run,), daemon=True, name="lazyrate-fetch"
        ).start()

    def _bcv_needed(self) -> bool:
        """BCV solo si falta la tasa de hoy (Caracas) o el último fetch tiene > 1 hora."""
        if not self.cfg.bcv.enabled or not self.cfg.bcv.currencies:
            return False
        row = store.latest("bcv", self.cfg.bcv.currencies[0])
        if row is None or row.value_date < today_caracas():
            return True
        age_minutes = (now_utc() - row.fetched_at).total_seconds() / 60
        return age_minutes > BCV_MAX_AGE_MINUTES

    def _fetch_worker(self, first_run: bool) -> None:
        if not self._fetch_busy.acquire(blocking=False):
            log.info("Actualización ya en curso; se omite este ciclo")
            return
        try:
            if self._bcv_needed():
                service.fetch_and_store(self.cfg)
            else:
                service.fetch_and_store(self.cfg, only_source="binance_p2p")
            no_bcv_rows = all(source != "bcv" for source, _ in store.sources_with_data())
            if first_run and self.cfg.bcv.enabled and self.cfg.bcv.currencies and no_bcv_rows:
                GLib.idle_add(self._refresh_from_thread)  # pinta lo recién traído antes
                self._initial_backfill()
            today = today_caracas()
            if self._last_purge_day != today:
                self._last_purge_day = today
                removed = store.purge(self.cfg.general.retention_days)
                if removed:
                    log.info("Purga diaria: %d filas eliminadas", removed)
        except Exception:
            log.exception("Fallo en el ciclo de actualización")
        finally:
            self._fetch_busy.release()
            GLib.idle_add(self._refresh_from_thread)

    def _initial_backfill(self) -> None:
        """Primer arranque sin datos BCV: importa los históricos oficiales (Excel)."""
        try:
            from lazyrate.providers import bcv

            log.info("Primer arranque: importando histórico del BCV")
            quotes = [q for q in bcv.backfill(self.cfg) if validate_quote(q)]
            inserted = store.insert_quotes(quotes)
            log.info("Backfill BCV: %d tasas leídas, %d nuevas", len(quotes), inserted)
        except Exception:
            log.exception("Fallo en el backfill inicial del BCV")

    def _refresh_from_thread(self) -> bool:
        self.refresh_ui()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------ UI (solo hilo GTK)

    def refresh_ui(self) -> None:
        label = service.bar_text(self.cfg)
        stale_text: str | None = None
        if self.cfg.bar.stale_mark:
            age = service.newest_fetch_age_minutes(self.cfg)
            if age is not None and age > 3 * self.cfg.general.refresh_minutes:
                label += " ⚠"
                stale_text = f"Último dato: hace {int(age)}m"
        self.indicator.set_label(label, label)
        self.indicator.set_menu(self._build_menu(stale_text))

    def _build_menu(self, stale_text: str | None) -> Gtk.Menu:
        menu = Gtk.Menu()
        today = today_caracas()
        if stale_text:
            item = Gtk.MenuItem(label=stale_text)
            item.set_sensitive(False)
            menu.append(item)
        for source, currency in service.enabled_pairs(self.cfg):
            if source == "bcv":
                name = f"BCV {currency}"
                row = store.latest(source, currency, on_or_before=today)
            else:
                name = f"P2P {currency}"
                row = store.latest(source, currency)
            if row is None:
                item = Gtk.MenuItem(label=f"{name}: sin datos")
                item.set_sensitive(False)
                menu.append(item)
                continue
            text = format_rate(row.rate, 4)
            item = Gtk.MenuItem(label=f"{name}: {text} ({row.value_date:%d/%m})")
            item.connect("activate", self._on_copy_rate, text)
            menu.append(item)
            if source == "bcv":
                nxt = store.upcoming(source, currency, after=today)
                if nxt is not None:
                    nxt_text = format_rate(nxt.rate, 4)
                    nxt_item = Gtk.MenuItem(
                        label=f"{name} mañana: {nxt_text} ({nxt.value_date:%d/%m})"
                    )
                    nxt_item.connect("activate", self._on_copy_rate, nxt_text)
                    menu.append(nxt_item)
        menu.append(Gtk.SeparatorMenuItem())

        update_item = Gtk.MenuItem(label="Actualizar ahora")
        update_item.connect("activate", self._on_update_now)
        menu.append(update_item)

        history_item = Gtk.MenuItem(label="Abrir historial")
        history_item.connect("activate", self._on_open_history)
        menu.append(history_item)

        reload_item = Gtk.MenuItem(label="Recargar configuración")
        reload_item.connect("activate", self._on_reload_config)
        menu.append(reload_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Salir")
        quit_item.connect("activate", self._on_quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    # ------------------------------------------------------------------ acciones del menú

    def _on_copy_rate(self, _item: Gtk.MenuItem, text: str) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()
        log.info("Copiado al portapapeles: %s", text)

    def _on_update_now(self, _item: Gtk.MenuItem) -> None:
        self.start_fetch()

    def _on_open_history(self, _item: Gtk.MenuItem) -> None:
        # Ruta absoluta de la TUI: la terminal hereda un PATH sin el venv/pipx,
        # así que "lazyrate" a secas fallaría dentro de gnome-terminal.
        tui = tui_command()
        for terminal in (["gnome-terminal", "--"], ["x-terminal-emulator", "-e"]):
            try:
                GLib.spawn_async(terminal + tui, flags=GLib.SpawnFlags.SEARCH_PATH)
                return
            except GLib.Error:
                continue
        log.warning("No se encontró un emulador de terminal para abrir la TUI")

    def _on_reload_config(self, _item: Gtk.MenuItem) -> None:
        self.reload_config()

    def _on_quit(self, _item: Gtk.MenuItem) -> None:
        Gtk.main_quit()

    # ------------------------------------------------------------------ configuración

    def _watch_config(self) -> None:
        gfile = Gio.File.new_for_path(str(config_mod.config_path()))
        self._config_monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._config_monitor.connect("changed", self._on_config_changed)

    def _on_config_changed(
        self,
        _monitor: Gio.FileMonitor,
        _file: Gio.File,
        _other: Gio.File | None,
        event: Gio.FileMonitorEvent,
    ) -> None:
        if event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED):
            self.reload_config()

    def reload_config(self) -> None:
        old_refresh = self.cfg.general.refresh_minutes
        self.cfg = config_mod.load(create=False)
        if self.cfg.general.refresh_minutes != old_refresh:
            self._arm_timer()
        self.refresh_ui()
        log.info("Configuración recargada")


def _on_exit_signal() -> bool:
    log.info("Señal recibida; saliendo")
    Gtk.main_quit()
    return GLib.SOURCE_REMOVE


def main() -> int:
    _setup_logging()
    lock = _acquire_single_instance_lock()
    if lock is None:
        log.info("Ya hay otra instancia del indicador corriendo; saliendo.")
        sys.exit(0)
    cfg = config_mod.load()
    app = IndicatorApp(cfg)
    for signum in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, _on_exit_signal)
    log.info("Indicador lazyrate iniciado (refresco cada %d min)", cfg.general.refresh_minutes)
    Gtk.main()
    del app  # mantiene vivas las referencias (indicador, monitor) hasta salir del bucle
    lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
