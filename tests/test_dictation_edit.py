"""Hold-a-key dictation and edit-by-voice."""
import sys
import types

import numpy as np

import config
import dictation
from skills import edit_text, text_tools


def test_dictation_types_what_was_said(monkeypatch):
    typed = []
    stt = types.ModuleType("audio.stt")
    stt.transcribe = lambda audio: "hello there"
    monkeypatch.setitem(sys.modules, "audio.stt", stt)
    monkeypatch.setattr(text_tools, "paste_text", lambda t: typed.append(t))
    dictation._frames[:] = [np.zeros(config.SAMPLE_RATE, dtype=np.float32)]
    dictation._finish()
    assert typed == ["hello there "]


def test_dictation_ignores_a_tap(monkeypatch):
    monkeypatch.setattr(text_tools, "paste_text", lambda t: (_ for _ in ()).throw(AssertionError))
    dictation._frames[:] = [np.zeros(100, dtype=np.float32)]
    dictation._finish()


def test_dictation_off_without_key(monkeypatch):
    monkeypatch.setattr(config, "DICTATION_KEY", None)
    assert dictation.start() is False


def test_edit_replaces_selection(monkeypatch):
    pasted = []
    monkeypatch.setattr(edit_text, "copy_selection", lambda: "hey wanna meet")
    monkeypatch.setattr(edit_text, "rewrite", lambda text, ins: "Would you like to meet?")
    monkeypatch.setattr(edit_text, "paste_text", pasted.append)
    out = edit_text.edit_selected_text({"instruction": "more formal"})
    assert pasted == ["Would you like to meet?"] and "Replaced" in out


def test_edit_needs_a_selection(monkeypatch):
    monkeypatch.setattr(edit_text, "copy_selection", lambda: "")
    assert "Nothing is selected" in edit_text.edit_selected_text({"instruction": "x"})


def test_copy_selection_restores_clipboard(monkeypatch):
    board = {"v": "old"}
    clip = types.SimpleNamespace(paste=lambda: board["v"], copy=lambda v: board.__setitem__("v", v))
    monkeypatch.setattr(text_tools, "_clip", lambda: clip)

    def ctrl_c(*keys):
        board["v"] = "selected words"
    monkeypatch.setattr(text_tools, "_pyautogui", lambda: types.SimpleNamespace(hotkey=ctrl_c))
    assert text_tools.copy_selection(wait=0) == "selected words"
    assert board["v"] == "old"
