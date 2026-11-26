"""Kokoro backup voice: used before Piper when set up, and Piper when it isn't."""
import numpy as np

import config
from audio import tts


class FakeKokoro:
    def create(self, text, voice, speed, lang):
        assert voice == config.KOKORO_VOICE and lang == "en-gb"
        return np.array([0.0, 0.5, -1.0, 2.0], dtype=np.float32), 24000


def test_kokoro_used_first(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_VOICE", "kokoro")
    monkeypatch.setattr(tts, "_kokoro", FakeKokoro())
    monkeypatch.setattr(tts, "_synth_piper", lambda t: (_ for _ in ()).throw(AssertionError("piper used")))
    audio, rate = tts._synth_local("Good evening, sir.")
    assert rate == 24000 and audio.dtype == np.int16
    assert list(audio) == [0, 16383, -32767, 32767]


def test_falls_back_to_piper(monkeypatch):
    piper = (np.zeros(3, dtype=np.int16), 22050)
    monkeypatch.setattr(tts, "_synth_piper", lambda t: piper)
    monkeypatch.setattr(config, "LOCAL_VOICE", "piper")
    assert tts._synth_local("hi") is piper
    # wanted but files not downloaded yet
    monkeypatch.setattr(config, "LOCAL_VOICE", "kokoro")
    monkeypatch.setattr(tts, "_kokoro", None)
    monkeypatch.setattr(tts, "KOKORO_DIR", "/nonexistent")
    assert tts._synth_local("hi") is piper


def test_kokoro_error_falls_back(monkeypatch):
    class Broken:
        def create(self, *a, **k):
            raise RuntimeError("boom")
    piper = (np.zeros(3, dtype=np.int16), 22050)
    monkeypatch.setattr(config, "LOCAL_VOICE", "kokoro")
    monkeypatch.setattr(tts, "_kokoro", Broken())
    monkeypatch.setattr(tts, "_synth_piper", lambda t: piper)
    assert tts._synth_local("hi") is piper
