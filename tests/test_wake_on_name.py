"""Waking on just "Jarvis": short isolated words are checked, sentences aren't."""
import importlib
import sys
import types

import numpy as np
import pytest

import config


class FakeModel:
    def __init__(self, **kw):
        self.models = {"hey_jarvis": None}

    def predict(self, chunk):
        return {"hey_jarvis": 0.0}

    def reset(self):
        pass


@pytest.fixture
def ww(monkeypatch):
    oww = types.ModuleType("openwakeword")
    oww.utils = types.SimpleNamespace(download_models=lambda: None)
    model_mod = types.ModuleType("openwakeword.model")
    model_mod.Model = FakeModel
    monkeypatch.setitem(sys.modules, "openwakeword", oww)
    monkeypatch.setitem(sys.modules, "openwakeword.model", model_mod)
    monkeypatch.delitem(sys.modules, "audio.wakeword", raising=False)
    monkeypatch.setattr(config, "WAKE_VERIFIER", None)
    mod = importlib.import_module("audio.wakeword")
    yield mod
    sys.modules.pop("audio.wakeword", None)


@pytest.mark.parametrize("text,expected", [
    ("Jarvis.", True), ("Jarvis?", True), ("Hey, Jarvis!", True), ("okay jarvis", True), ("Jervis", True),
    ("Travis", False), ("Jarvis, what time is it?", False), ("thanks", False), ("", False),
])
def test_is_name(ww, text, expected):
    assert ww.is_name(text) is expected


def chunks(pattern):
    """'_' = 80 ms of quiet, 'x' = 80 ms of speech."""
    return [(np.full(1280, 1 if c == "x" else 0, dtype=np.int16), c == "x") for c in pattern]


def run(ww, pattern):
    spot, found = ww.NameSpotter(), []
    for chunk, speaking in chunks(pattern):
        word = spot.feed(chunk, speaking)
        if word is not None:
            found.append(int((word != 0).sum() // 1280))
    return found


def test_short_word_with_pauses_is_a_candidate(ww):
    assert run(ww, "_____xxxxxx_____") == [6]          # ~0.5 s word


def test_sentences_and_blips_are_not(ww):
    assert run(ww, "_____" + "x" * 40 + "_____") == []    # 3 s of talking
    assert run(ww, "_____x_____") == []                    # a click
    assert run(ww, "xxxxxxxxxx__xxxx_____") == []          # word right after talking, no pause


def test_name_wakes_him(ww, monkeypatch):
    audio = [c for c, _ in chunks("_____xxxxxx_____")]
    stream = types.SimpleNamespace(read=lambda n: (audio.pop(0)[:, None] if audio else np.zeros((1280, 1), np.int16),
                                                   False))
    monkeypatch.setattr(ww, "is_speech", lambda c: bool(c.any()))
    heard = []
    monkeypatch.setattr(ww, "_heard_name", lambda a: heard.append(len(a)) or True)
    monkeypatch.setattr(config, "WAKE_ON_NAME", True)
    monkeypatch.setattr(config, "ROOM_CONTEXT", False)
    assert ww.wait_for_wake_word(stream) is None
    assert heard
