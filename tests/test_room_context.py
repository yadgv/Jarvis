"""'Third person in the room': off by default; when on, the talk before the
wake word becomes a one-off note, never history."""
import sys
import types

import numpy as np

import config
import room_context


def test_off_by_default():
    assert config.ROOM_CONTEXT is False
    assert room_context.start() is None


def test_transcribes_room_audio(monkeypatch):
    monkeypatch.setattr(config, "ROOM_CONTEXT", True)
    ww = types.ModuleType("audio.wakeword")
    ww.take_room_audio = lambda: np.zeros(config.SAMPLE_RATE * 5, dtype=np.float32)
    stt = types.ModuleType("audio.stt")
    stt.transcribe = lambda a: "I think the Leafs will win tonight for sure"
    monkeypatch.setitem(sys.modules, "audio.wakeword", ww)
    monkeypatch.setitem(sys.modules, "audio.stt", stt)
    import audio
    monkeypatch.setattr(audio, "wakeword", ww, raising=False)
    monkeypatch.setattr(audio, "stt", stt, raising=False)
    text = room_context.result(room_context.start())
    assert "Leafs" in text
    assert "Background, not a request" in room_context.note(text)


def test_short_snippets_are_dropped():
    holder = {"done": types.SimpleNamespace(wait=lambda t: True), "text": "uh huh"}
    assert room_context.result(holder) == ""
