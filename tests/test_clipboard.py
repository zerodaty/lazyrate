"""Tests del portapapeles: selección de herramienta y comportamiento sin ninguna."""

from __future__ import annotations

import subprocess

import pytest

from lazyrate import clipboard


@pytest.fixture(autouse=True)
def _no_display(monkeypatch):
    """Parte de un entorno sin sesión gráfica; cada test declara lo que hay."""
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)


def test_prefers_wl_copy_on_wayland(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert clipboard._candidates()[0] == ["wl-copy"]


def test_prefers_xclip_on_x11(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    assert clipboard._candidates()[0] == ["xclip", "-selection", "clipboard"]


def test_copy_uses_first_available_tool(monkeypatch):
    calls: list[tuple[list[str], bytes]] = []

    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name == "wl-copy")

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs["input"]))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
    assert clipboard.copy("668,50") is True
    assert calls == [(["wl-copy"], b"668,50")]


def test_copy_falls_through_when_tool_fails(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    # xclip está pero falla; xsel está y funciona
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name in ("xclip", "xsel"))
    used: list[str] = []

    def fake_run(argv, **kwargs):
        used.append(argv[0])
        if argv[0] == "xclip":
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
    assert clipboard.copy("x") is True
    assert used == ["xclip", "xsel"]


def test_copy_returns_false_without_any_tool(monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", lambda _name: None)
    assert clipboard.copy("x") is False
    assert clipboard.available_tool() is None


def test_copy_never_raises_on_oserror(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name == "wl-copy")

    def boom(*_a, **_k):
        raise OSError("no such tool")

    monkeypatch.setattr(clipboard.subprocess, "run", boom)
    assert clipboard.copy("x") is False
