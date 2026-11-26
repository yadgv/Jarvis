"""The offline voice: Kokoro or Piper, picked with one setting (OFFLINE_VOICE)."""
import numpy as np

import config
from audio import tts
from brain import settings


class FakeKokoro:
    def __init__(self):
        self.calls = []

    def create(self, text, voice, speed, lang):
        self.calls.append((voice, lang))
        return np.array([0.0, 0.5, -1.0, 2.0], dtype=np.float32), 24000


def use(monkeypatch, name, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "OFFLINE_VOICE", name)


def test_kokoro_used_first(monkeypatch, tmp_path):
    use(monkeypatch, "fable", tmp_path)
    fake = FakeKokoro()
    monkeypatch.setattr(tts, "_kokoro", fake)
    monkeypatch.setattr(tts, "_synth_piper", lambda t: (_ for _ in ()).throw(AssertionError("piper used")))
    audio, rate = tts._synth_local("Good evening, sir.")
    assert rate == 24000 and audio.dtype == np.int16
    assert list(audio) == [0, 16383, -32767, 32767]
    assert fake.calls == [("bm_fable", "en-gb")]


def test_american_voices_use_american_english(monkeypatch, tmp_path):
    use(monkeypatch, "michael", tmp_path)
    fake = FakeKokoro()
    monkeypatch.setattr(tts, "_kokoro", fake)
    tts._synth_local("hi")
    assert fake.calls == [("am_michael", "en-us")]


def test_one_setting_picks_the_engine(monkeypatch, tmp_path):
    use(monkeypatch, "george", tmp_path)
    assert tts.offline_voice() == ("kokoro", "bm_george")
    use(monkeypatch, "alan", tmp_path)
    assert tts.offline_voice() == ("piper", "en_GB-alan-medium")
    use(monkeypatch, "bm_daniel", tmp_path)   # raw ids work too
    assert tts.offline_voice() == ("kokoro", "bm_daniel")


def test_falls_back_to_piper(monkeypatch, tmp_path):
    piper = (np.zeros(3, dtype=np.int16), 22050)
    monkeypatch.setattr(tts, "_synth_piper", lambda t: piper)
    use(monkeypatch, "alan", tmp_path)
    assert tts._synth_local("hi") is piper
    # Kokoro wanted but its files aren't downloaded yet
    use(monkeypatch, "fable", tmp_path)
    monkeypatch.setattr(tts, "_kokoro", None)
    monkeypatch.setattr(tts, "KOKORO_DIR", "/nonexistent")
    assert tts._synth_local("hi") is piper


def test_kokoro_error_falls_back(monkeypatch, tmp_path):
    class Broken:
        def create(self, *a, **k):
            raise RuntimeError("boom")
    piper = (np.zeros(3, dtype=np.int16), 22050)
    use(monkeypatch, "fable", tmp_path)
    monkeypatch.setattr(tts, "_kokoro", Broken())
    monkeypatch.setattr(tts, "_synth_piper", lambda t: piper)
    assert tts._synth_local("hi") is piper


def test_best_quality_model_preferred(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OFFLINE_VOICE_QUALITY", "best")
    assert tts._kokoro_model_names()[0] == "kokoro-v1.0.onnx"
    monkeypatch.setattr(config, "OFFLINE_VOICE_QUALITY", "small")
    assert tts._kokoro_model_names() == ["kokoro-v1.0.int8.onnx", "kokoro-v1.0.onnx"]
    # Only the small one downloaded: it's used until the best one arrives.
    monkeypatch.setattr(config, "OFFLINE_VOICE_QUALITY", "best")
    (tmp_path / "kokoro-v1.0.int8.onnx").write_bytes(b"x")
    (tmp_path / "voices-v1.0.bin").write_bytes(b"x")
    monkeypatch.setattr(tts, "KOKORO_DIR", str(tmp_path))
    monkeypatch.setattr(tts, "_kokoro", None)
    loaded = []
    import sys
    import types
    monkeypatch.setitem(sys.modules, "kokoro_onnx",
                        types.SimpleNamespace(Kokoro=lambda m, v: loaded.append(m) or object()))
    assert tts._load_kokoro() is not None
    assert loaded[0].endswith("kokoro-v1.0.int8.onnx")
    monkeypatch.setattr(tts, "_kokoro", None)


def test_piper_voice_url():
    sent = []
    import os
    old = tts._download
    try:
        tts._download = lambda url, path: sent.append(url)
        tts._download_piper("en_GB-northern_english_male-medium")
    finally:
        tts._download = old
    assert sent[0] == ("https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/"
                       "northern_english_male/medium/en_GB-northern_english_male-medium.onnx")
    assert all(not os.path.exists(u) for u in sent)


def test_change_and_try_by_voice(monkeypatch, tmp_path):
    use(monkeypatch, "fable", tmp_path)
    assert "now george" in settings.change("offline_voice", "George voice")
    assert tts.offline_voice() == ("kokoro", "bm_george")
    assert "Unknown" in settings.change("offline_voice", "gandalf")
    from skills import personality
    played = []
    monkeypatch.setattr(tts, "preview", lambda name, text=tts.SAMPLE: played.append(name) or "Played.")
    assert "keep" in personality.try_offline_voice({"name": "lewis"})
    assert played == ["lewis"]
