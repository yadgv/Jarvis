"""Keyboard shortcuts: Ctrl+Alt+J to type to Jarvis, Ctrl+Alt+H to show/hide the text."""
import os

import pytest

import hotkeys
from brain import settings


def test_normal_shortcuts():
    assert hotkeys.normal("Ctrl + Alt + J") == "ctrl+alt+j"
    assert hotkeys.normal("alt+ctrl+h") == "ctrl+alt+h"
    assert hotkeys.normal("control+shift+space") == "ctrl+shift+space"
    assert hotkeys.normal("F8") == "f8" and hotkeys.normal("win+alt+k") == "alt+win+k"
    for bad in ("", "j", "ctrl+alt", "ctrl+banana", "hyper+j", "ctrl+ctrl+j"):
        assert hotkeys.normal(bad) == "", bad


def test_pynput_format():
    assert hotkeys.to_pynput("ctrl+alt+j") == "<ctrl>+<alt>+j"
    assert hotkeys.to_pynput("ctrl+shift+space") == "<ctrl>+<shift>+<space>"
    assert hotkeys.to_pynput("f8") == "<f8>"


def test_pick_skips_clashes():
    assert hotkeys.pick({}) == {"ctrl+alt+j": "type_key", "ctrl+alt+h": "panel_key"}
    assert hotkeys.pick({"type_key": "f9"}, dictation_key="f9") == {"ctrl+alt+h": "panel_key"}
    assert hotkeys.pick({"type_key": "ctrl+alt+h"}) == {"ctrl+alt+h": "type_key"}
    assert hotkeys.pick({"type_key": "nonsense"}) == {"ctrl+alt+j": "type_key", "ctrl+alt+h": "panel_key"}


def test_saved_in_settings():
    assert settings.app_defaults()["type_key"] == "ctrl+alt+j"
    assert settings._clean("type_key", "Ctrl+Shift+K", "ctrl+alt+j") == "ctrl+shift+k"
    assert settings._clean("panel_key", "banana", "ctrl+alt+h") == "ctrl+alt+h"


def test_start_without_pynput_is_harmless(monkeypatch):
    import builtins
    real = builtins.__import__

    def no_pynput(name, *a, **k):
        if name.startswith("pynput"):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_pynput)
    assert hotkeys.start({}, lambda a: None) == {}


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a screen")
def test_widget_shortcuts(monkeypatch):  # pragma: no cover - only where Tk has a display
    tk = pytest.importorskip("tkinter")
    import gui
    saved = []
    monkeypatch.setattr(settings, "save", lambda v: saved.append(v) or v)
    monkeypatch.setattr(hotkeys, "start", lambda *a, **k: {})
    root = tk.Tk()
    try:
        w = gui.JarvisWidget(root)
        w.prefs = {**w.prefs, "show_panel": True}
        w.events.put(("hotkey", "type_key"))
        w.tick()
        assert w.typing and w.expanded
        w.on_hotkey("panel_key")
        assert not w.prefs["show_panel"] and not w.expanded and not w.typing and saved[-1] == {"show_panel": False}
        w.on_hotkey("panel_key")
        assert w.prefs["show_panel"] and w.expanded and saved[-1] == {"show_panel": True}
    finally:
        root.destroy()


def test_stuck_modifier_does_not_fire(monkeypatch, capsys):
    """pynput thought Ctrl+Alt were held after a missed key-up: typing "h" hid the panel."""
    fired = []
    import sys
    monkeypatch.setattr(sys, "platform", "win32")
    down = set()
    monkeypatch.setattr(hotkeys, "_down", lambda vk: vk in down)
    hotkeys._fire("ctrl+alt+h", "panel_key", fired.append)
    assert fired == [] and "weren't really held" in capsys.readouterr().out
    down |= {0x11, 0x12}
    hotkeys._fire("ctrl+alt+h", "panel_key", fired.append)
    assert fired == ["panel_key"]
    down.clear()
    down |= {0x11, 0x12, 0x5C}            # right Windows key counts too
    hotkeys._fire("ctrl+alt+win+k", "type_key", fired.append)
    assert fired == ["panel_key", "type_key"]


def test_other_systems_trust_pynput(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "platform", "linux")
    fired = []
    hotkeys._fire("ctrl+alt+j", "type_key", fired.append)
    assert fired == ["type_key"]
