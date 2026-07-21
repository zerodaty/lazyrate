"""Copiado al portapapeles del sistema.

Textual copia vía OSC 52 (una secuencia de escape del terminal) que muchos
emuladores —GNOME Terminal / VTE entre ellos— ignoran por defecto, así que
"copiar" no hace nada. Para que funcione de forma fiable se delega en una
herramienta del sistema: ``wl-copy`` (Wayland) o ``xclip``/``xsel`` (X11).
El llamador puede caer a OSC 52 si aquí ninguna está disponible.
"""

from __future__ import annotations

import os
import shutil
import subprocess

# (comando, argv) por herramienta: lee el texto por stdin y lo pone en el portapapeles.
_WL = ["wl-copy"]
_XCLIP = ["xclip", "-selection", "clipboard"]
_XSEL = ["xsel", "--clipboard", "--input"]


def _candidates() -> list[list[str]]:
    """Comandos a intentar, priorizando según el tipo de sesión."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return [_WL, _XCLIP, _XSEL]
    if os.environ.get("DISPLAY"):
        return [_XCLIP, _XSEL, _WL]
    return [_WL, _XCLIP, _XSEL]


def available_tool() -> str | None:
    """Nombre de la primera herramienta de portapapeles instalada, o None."""
    for argv in _candidates():
        if shutil.which(argv[0]) is not None:
            return argv[0]
    return None


def copy(text: str) -> bool:
    """Copia ``text`` al portapapeles con una herramienta del sistema.

    Devuelve True si alguna aceptó el texto; False si ninguna está instalada o
    todas fallaron. Nunca lanza: el copiado es un extra, no debe tumbar la TUI.
    """
    payload = text.encode("utf-8")
    for argv in _candidates():
        if shutil.which(argv[0]) is None:
            continue
        try:
            # wl-copy/xclip/xsel se desprenden al fondo tras leer stdin; el timeout
            # es un seguro por si alguno se quedara en primer plano.
            subprocess.run(
                argv,
                input=payload,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return True
    return False
