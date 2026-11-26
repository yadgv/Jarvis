"""The orb's Settings window: saved settings, put into config, and the
whiteboard brought to the front."""
import types

import pytest

import config
from brain import memory, settings


@pytest.fixture
def mem(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    for attr in settings._ATTRS:  # apply() changes config: put it back after each test
        if hasattr(config, attr):
            monkeypatch.setattr(config, attr, getattr(config, attr))
    return tmp_path


def test_defaults_come_from_config(mem):
    s = settings.app()
    assert s["show_panel"] and s["show_text_box"] and s["orb_size"] == "medium"
    assert s["wake_sensitivity"] == settings._sensitivity(settings._ORIGINAL["WAKE_THRESHOLD"])
    assert s["position"] is None and s["telegram"] is True


def test_sensitivity_and_threshold_match():
    assert settings.threshold(5) == 0.5 and settings._sensitivity(0.5) == 5
    assert settings.threshold(10) < settings.threshold(1)   # more sensitive = lower threshold
    assert settings.threshold(99) == settings.threshold(10)


def test_save_cleans_values_and_keeps_them(mem):
    saved = settings.save({"show_text_box": "false", "orb_color": "#AABBCC", "listening_color": "red",
                           "orb_size": "huge", "panel_seconds": "500", "followup_seconds": 3.7,
                           "corner": "bottom-left", "position": ["10", 20], "temperature_unit": "F",
                           "nonsense": 1})
    assert saved["show_text_box"] is False and saved["orb_color"] == "#aabbcc"
    assert "nonsense" not in saved
    s = settings.app()
    assert s["listening_color"] == settings.COLOURS["listening_color"]  # not a colour: default kept
    assert s["orb_size"] == "medium" and s["panel_seconds"] == 60 and s["followup_seconds"] == 3
    assert s["position"] == [10, 20] and s["corner"] == "bottom-left" and s["temperature_unit"] == "fahrenheit"


def test_save_puts_choices_into_config(mem, monkeypatch):
    monkeypatch.setattr(settings, "_ORIGINAL", {**settings._ORIGINAL, "LOCAL_MODEL": "",
                                                "DUCK_APPS": ["Spotify.exe"]})
    settings.save({"wake_sensitivity": 8, "wake_chime": False, "offline_mode": True, "room_mode": True,
                   "telegram": False, "morning_briefing": False, "local_model": True, "ducking": False,
                   "followup_seconds": 0})
    assert config.WAKE_THRESHOLD == settings.threshold(8) and config.WAKE_CHIME is False
    assert config.OFFLINE_MODE and config.ROOM_CONTEXT and config.TELEGRAM_ON is False
    assert config.MORNING_BRIEFING is False and config.FOLLOWUP_SECONDS == 0
    assert config.LOCAL_MODEL and config.DUCK_APPS == []
    settings.save({"ducking": True, "local_model": False})
    assert config.DUCK_APPS == ["Spotify.exe"] and config.LOCAL_MODEL == ""


def test_apply_leaves_unsaved_settings_alone(mem, monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_SECONDS", 0)   # e.g. changed in config.py or by a test
    settings.save({"orb_size": "large"})
    assert config.FOLLOWUP_SECONDS == 0


def test_microphone_by_name(mem, monkeypatch):
    fake = types.SimpleNamespace(query_devices=lambda: [
        {"name": "Speakers", "max_input_channels": 0}, {"name": "USB mic", "max_input_channels": 1}])
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake)
    assert settings.microphones() == ["USB mic"]
    settings.save({"mic": "USB mic"})
    assert config.MIC_DEVICE == 1
    settings.save({"mic": "Gone mic"})
    assert config.MIC_DEVICE is None
    settings.save({"mic": ""})
    assert config.MIC_DEVICE == settings._ORIGINAL["MIC_DEVICE"]


def test_voice_settings_save_through_the_same_checks(mem):
    settings.save({"voice": "jarvis", "offline_voice": "george", "speed": 9, "style": "casual",
                   "call_me": "Ziad"})
    s = settings.load()
    assert s["offline_voice"] == "george" and s["speed"] == settings.MAX_SPEED
    assert s["style"] == "casual" and s["call_me"] == "Ziad"
    settings.save({"style": "grumpy"})   # not a style: stays as it was
    assert settings.load()["style"] == "casual"


def test_voice_reset_keeps_the_window_settings(mem):
    settings.save({"style": "casual", "orb_size": "large"})
    settings.change("reset", "")
    assert settings.load()["style"] == config.STYLE
    assert settings.app()["orb_size"] == "large"


def test_reset_all(mem):
    settings.save({"style": "brief", "wake_chime": False, "orb_size": "small"})
    settings.reset_all()
    assert memory._read(settings.FILE, None) == {}
    assert config.WAKE_CHIME == settings._ORIGINAL["WAKE_CHIME"]
    assert settings.app()["orb_size"] == "medium"


def test_telegram_off_in_settings(mem, monkeypatch):
    import telegram_bot
    monkeypatch.setattr(telegram_bot, "_token", lambda: "t")
    monkeypatch.setattr(telegram_bot, "_thread", None)
    monkeypatch.setattr(config, "TELEGRAM_ON", False)
    assert telegram_bot.start() is False


def test_online_voice_preview(monkeypatch):
    from audio import tts
    import numpy as np
    sent, played = [], []

    class Reply:
        content = np.zeros(10, dtype=np.int16).tobytes()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(config, "VOICES", {"jarvis": "id-1"})
    monkeypatch.setattr(tts, "_fish_request", lambda text, stream, voice=None: sent.append(voice) or Reply())
    monkeypatch.setattr(tts, "play", played.append)
    assert "Played" in tts.preview_online("Jarvis")
    assert sent == ["id-1"] and played
    assert "no online voice" in tts.preview_online("nobody")


def test_whiteboard_comes_to_the_front(monkeypatch):
    from skills import whiteboard as wb
    front = []
    monkeypatch.setattr(wb, "_app_browser", lambda: "edge")
    monkeypatch.setattr(wb.subprocess, "Popen", lambda cmd: None)
    monkeypatch.setattr(wb, "url", lambda: "http://127.0.0.1:1/")
    monkeypatch.setattr(wb, "_to_front", lambda wait=15.0: front.append(wait))
    monkeypatch.setattr(wb, "_opened", False)
    wb.open_window()
    assert front == [15.0]
    monkeypatch.setattr(wb, "window_open", lambda: True)   # already open behind other windows
    wb.open_window()
    assert front == [15.0, 3]


def test_bring_to_front_pins_and_focuses(monkeypatch):
    from skills import whiteboard as wb
    calls = []

    class User32:
        def __getattr__(self, name):
            return lambda *a: calls.append((name, a)) or {"IsIconic": 1, "GetForegroundWindow": 7,
                                                           "GetWindowThreadProcessId": 9,
                                                           "AttachThreadInput": 1}.get(name, 0)

    kernel = types.SimpleNamespace(GetCurrentThreadId=lambda: 3)
    fake_ctypes = types.SimpleNamespace(windll=types.SimpleNamespace(kernel32=kernel))
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake_ctypes)
    wb._raise(User32(), 42, pin=True)
    names = [n for n, _ in calls]
    assert ("ShowWindow", (42, 9)) in calls                       # restored from minimised
    assert ("SetWindowPos", (42, -1, 0, 0, 0, 0, 0x43)) in calls  # on top of everything
    assert ("SetWindowPos", (42, -2, 0, 0, 0, 0, 0x43)) not in calls
    assert names.index("SetForegroundWindow") > names.index("AttachThreadInput")
    assert calls[-2][0] != "AttachThreadInput" or calls[-2][1][2] is False
    calls.clear()
    wb._raise(User32(), 42, pin=False)                            # in front, but not pinned
    assert ("SetWindowPos", (42, -2, 0, 0, 0, 0, 0x43)) in calls


def test_not_windows_no_front(monkeypatch):
    from skills import whiteboard as wb
    monkeypatch.setattr(wb.sys, "platform", "linux")
    assert wb._to_front() is False


def test_window_code_compiles():
    import py_compile
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("gui.py", "settings_window.py"):
        py_compile.compile(os.path.join(here, name), doraise=True)
