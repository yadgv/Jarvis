"""Saying "Jarvis" mid-conversation continues it; hearing hints for his words."""
import types

import numpy as np
import pytest

import config
import main
from tests.test_conversation import _run


@pytest.mark.parametrize("text, addressed, rest", [
    ("Jarvis", True, ""), ("Uh, Jarvis.", True, ""), ("Jarvis?", True, ""),
    ("Jarvis, and what about Friday?", True, "And what about Friday?"),
    ("what do you think, Jarvis?", True, "what do you think?"),
    ("Travis clear the whiteboard", True, "Clear the whiteboard"),
    ("Travis is coming over later", False, "Travis is coming over later"),
    ("Jarvis's voice is nice", True, "Jarvis's voice is nice"),
    ("so I told Jarvis about it", True, "so I told Jarvis about it"),
    ("open spotify", False, "open spotify"),
])
def test_strip_name(text, addressed, rest):
    assert main.strip_name(text) == (addressed, rest)


def test_name_mid_conversation_continues_it(monkeypatch):
    calls, spoken, recorded = _run(monkeypatch, [
        "what's the weather", "Jarvis, and tomorrow?", "and saturday", None])
    # Same conversation: said to him by name, so never treated as chatter he may ignore.
    assert calls == [("what's the weather", False), ("And tomorrow?", False), ("and saturday", True)]
    assert not [s for s in spoken if "sir?" in s or "catch" in s]


def test_name_then_pause_waits_for_the_rest(monkeypatch):
    calls, spoken, recorded = _run(monkeypatch, ["what's the weather", "Jarvis.", "and tomorrow?", None])
    assert calls == [("what's the weather", False), ("and tomorrow?", False)]
    assert not [s for s in spoken if "sir?" in s]      # no "Yes, sir?", no restart
    assert len(recorded) == 4 and all(t for t in recorded[1:])   # kept listening as a follow-up


def test_name_then_shut_down_still_shuts_down(monkeypatch):
    calls, spoken, _ = _run(monkeypatch, ["what's the weather", "Jarvis, shut down"])
    assert "Powering down. Goodbye, sir." in spoken


def test_bye_jarvis_just_closes(monkeypatch):
    calls, spoken, _ = _run(monkeypatch, ["what's the weather", "bye jarvis", None])
    assert "Very good, sir." in spoken


def test_hearing_hint_has_his_words(monkeypatch, tmp_path):
    from audio import stt
    from brain import memory
    from skills import vocab
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    vocab.learn_word({"word": "Kirchhoff"})
    memory._write("canvas.json", {"course_names": ["MECE 2320 Thermodynamics"]})
    hint = stt.hint()
    assert "breadboard" in hint and "Kirchhoff" in hint and "MECE 2320 Thermodynamics" in hint
    assert vocab.forget_word({"word": "kirchhoff"}).startswith("Forgotten")
    assert "Kirchhoff" not in stt.hint()


def test_transcribe_passes_hint_and_beam(monkeypatch):
    from audio import stt
    seen = []

    class Model:
        def transcribe(self, audio, **k):
            seen.append(k)
            return iter([types.SimpleNamespace(text=" the breadboard ")]), None
    monkeypatch.setattr(stt, "_model", Model())
    stt._ready.set()
    assert stt.transcribe(np.zeros(1600, np.float32)) == "the breadboard"
    assert "breadboard" in seen[-1]["initial_prompt"] and seen[-1]["beam_size"] == config.WHISPER_BEAM_SIZE
    assert seen[-1]["vad_parameters"]["speech_pad_ms"] >= 300
    stt.transcribe(np.zeros(1600, np.float32), hints=False)   # the "was that his name?" check
    assert "initial_prompt" not in seen[-1]


def test_hint_echo_is_dropped(monkeypatch):
    from audio import stt

    class Model:
        def transcribe(self, audio, **k):
            return iter([types.SimpleNamespace(text="Talking to Jarvis about breadboard, Arduino.")]), None
    monkeypatch.setattr(stt, "_model", Model())
    stt._ready.set()
    assert stt.transcribe(np.zeros(1600, np.float32)) == ""


def test_falls_back_to_smaller_model(monkeypatch):
    from audio import stt
    tried = []

    def load(name):
        tried.append(name)
        if name == "small.en":
            raise OSError("no internet")
        return "model"
    monkeypatch.setattr(stt, "_load_one", load)
    monkeypatch.setattr(config, "WHISPER_MODEL", "small.en")
    assert stt._load() == "model" and tried == ["small.en", "base.en"]
