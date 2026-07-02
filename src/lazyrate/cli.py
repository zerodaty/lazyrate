"""CLI de lazyrate: sin argumentos abre la TUI; subcomandos para uso en terminal/scripts."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from lazyrate import __version__, store
from lazyrate import config as config_mod
from lazyrate.format import format_rate
from lazyrate.providers.base import today_caracas, validate_quote

# El nombre público en la CLI es "binance"; internamente la fuente es "binance_p2p"
_SOURCE_MAP = {"bcv": "bcv", "binance": "binance_p2p"}

def tui_command() -> list[str]:
    """Comando para abrir la TUI desde otro proceso (p.ej. el indicador).

    No depende del PATH del usuario: en desarrollo (venv) o pipx el script
    'lazyrate' vive junto al intérprete en ejecución; instalado por .deb está
    en /usr/bin (que también es hermano de /usr/bin/python3).
    """
    sibling = Path(sys.executable).with_name("lazyrate")
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return [str(sibling)]
    found = shutil.which("lazyrate")
    if found:
        return [found]
    return [sys.executable, "-m", "lazyrate"]


AUTOSTART_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=lazyrate indicator
Comment=Tasa BCV y Binance P2P en la barra de GNOME
Exec={exec_path}
Icon=lazyrate
X-GNOME-Autostart-Delay=10
"""


def _indicator_command() -> str:
    """Ruta absoluta del indicador para el .desktop de autostart.

    El PATH de la sesión de GNOME no siempre incluye ~/.local/bin al arrancar,
    así que 'lazyrate-indicator' a secas puede fallar con pipx.
    """
    sibling = Path(sys.executable).with_name("lazyrate-indicator")
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling)
    return shutil.which("lazyrate-indicator") or "lazyrate-indicator"


def _autostart_desktop() -> str:
    return AUTOSTART_DESKTOP_TEMPLATE.format(exec_path=_indicator_command())


def _print_current(cfg: config_mod.Config, only_source: str | None) -> bool:
    """Imprime el estado vigente por fuente/moneda. Devuelve si mostró algo."""
    today = today_caracas()
    shown = False
    if cfg.bcv.enabled and only_source in (None, "bcv"):
        for currency in cfg.bcv.currencies:
            row = store.latest("bcv", currency, on_or_before=today)
            if row:
                print(
                    f"BCV {currency}: {format_rate(row.rate, 4)} Bs"
                    f" (vigente {row.value_date:%d/%m/%Y})"
                )
                shown = True
            upcoming = store.upcoming("bcv", currency, after=today)
            if upcoming:
                print(
                    f"BCV {currency} próxima: {format_rate(upcoming.rate, 4)} Bs"
                    f" (vigente {upcoming.value_date:%d/%m/%Y})"
                )
    if cfg.binance.enabled and only_source in (None, "binance_p2p"):
        row = store.latest("binance_p2p", cfg.binance.asset)
        if row:
            ads = ""
            if row.meta.get("ads_used"):
                ads = f" · {row.meta['ads_used']}/{row.meta.get('ads_total', '?')} anuncios"
            print(f"Binance P2P {cfg.binance.asset}: {format_rate(row.rate, 2)} Bs{ads}")
            shown = True
    return shown


def _cmd_fetch(args: argparse.Namespace) -> int:
    from lazyrate import service

    cfg = config_mod.load()
    only_source = _SOURCE_MAP.get(args.source) if args.source else None
    accepted = service.fetch_and_store(cfg, only_source=only_source)
    if not accepted:
        print("No se obtuvo ninguna tasa nueva (¿sin red?).", file=sys.stderr)
    if not _print_current(cfg, only_source):
        print("Sin datos guardados todavía. Prueba: lazyrate backfill", file=sys.stderr)
        return 1
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    only_source = _SOURCE_MAP.get(args.source) if args.source else None
    pairs = store.sources_with_data()
    if only_source:
        pairs = [p for p in pairs if p[0] == only_source]
    if args.currency:
        pairs = [p for p in pairs if p[1] == args.currency.upper()]
    if not pairs:
        print("Sin histórico. Prueba: lazyrate fetch  o  lazyrate backfill", file=sys.stderr)
        return 1
    for source, currency in pairs:
        series = store.daily_series(source, currency, days=args.days)
        label = "BCV" if source == "bcv" else "Binance P2P"
        print(f"\n== {label} {currency} — últimos {args.days} días ({len(series)} datos) ==")
        for day, rate in series:
            print(f"{day:%d/%m/%Y}  {format_rate(rate, 4)}")
    return 0


def _cmd_backfill(args: argparse.Namespace) -> int:
    from lazyrate.providers import bcv

    cfg = config_mod.load()
    print("Descargando históricos del BCV (Excel trimestrales)...")
    quotes = [q for q in bcv.backfill(cfg, year=args.year) if validate_quote(q)]
    inserted = store.insert_quotes(quotes)
    print(f"Backfill BCV: {len(quotes)} tasas leídas, {inserted} nuevas guardadas.")
    return 0 if quotes else 1


def _cmd_autostart(args: argparse.Namespace) -> int:
    user_dir = config_mod.xdg_config_root() / "autostart"
    user_file = user_dir / "lazyrate-indicator.desktop"
    system_file = Path("/etc/xdg/autostart/lazyrate-indicator.desktop")
    if args.action == "enable":
        user_dir.mkdir(parents=True, exist_ok=True)
        user_file.write_text(_autostart_desktop(), encoding="utf-8")
        print(f"Autostart habilitado: {user_file}")
    elif args.action == "disable":
        if system_file.exists():
            # No podemos tocar /etc; un override de usuario con Hidden=true lo desactiva
            user_dir.mkdir(parents=True, exist_ok=True)
            user_file.write_text(_autostart_desktop() + "Hidden=true\n", encoding="utf-8")
            print(f"Autostart deshabilitado (override): {user_file}")
        elif user_file.exists():
            user_file.unlink()
            print("Autostart deshabilitado.")
        else:
            print("El autostart ya estaba deshabilitado.")
    else:  # status
        if user_file.exists():
            if "Hidden=true" in user_file.read_text(encoding="utf-8"):
                print("Autostart: deshabilitado (override de usuario)")
            else:
                print(f"Autostart: habilitado ({user_file})")
        elif system_file.exists():
            print(f"Autostart: habilitado (sistema: {system_file})")
        else:
            print("Autostart: deshabilitado")
    return 0


def _run_tui() -> int:
    try:
        from lazyrate.tui.app import LazyrateApp
    except ModuleNotFoundError as exc:
        print(f"La TUI requiere dependencias que faltan ({exc.name}).", file=sys.stderr)
        print("Instala con: pip install 'lazyrate[tui]'", file=sys.stderr)
        return 1
    LazyrateApp().run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lazyrate",
        description="Tasa BCV y Binance P2P (USDT/VES) en tu terminal y en la barra de GNOME.",
    )
    parser.add_argument("--version", action="version", version=f"lazyrate {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_fetch = sub.add_parser("fetch", help="consultar y guardar las tasas ahora")
    p_fetch.add_argument("--source", choices=["bcv", "binance"])

    p_hist = sub.add_parser("history", help="mostrar el histórico guardado")
    p_hist.add_argument("--days", type=int, default=30)
    p_hist.add_argument("--source", choices=["bcv", "binance"])
    p_hist.add_argument("--currency")

    p_back = sub.add_parser("backfill", help="importar histórico BCV desde los Excel oficiales")
    p_back.add_argument("--year", type=int, help="año a importar (default: el actual)")

    p_auto = sub.add_parser("autostart", help="gestionar el arranque automático del indicador")
    p_auto.add_argument("action", choices=["enable", "disable", "status"])

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if args.command is None:
        return _run_tui()
    handlers = {
        "fetch": _cmd_fetch,
        "history": _cmd_history,
        "backfill": _cmd_backfill,
        "autostart": _cmd_autostart,
    }
    return handlers[args.command](args)
