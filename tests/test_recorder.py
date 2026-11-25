"""Recording stops when you stop talking, even with chatter in the background."""
import numpy as np

import config
from audio import recorder


class FakeStream:
    def __init__(self, levels):
        self.levels = list(levels)
        self.reads = 0

    def read(self, n):
        self.reads += 1
        level = self.levels.pop(0) if self.levels else 0
        rng = np.random.default_rng(self.reads)
        chunk = (rng.choice([-1, 1], n) * level).astype(np.int16).reshape(-1, 1)
        return chunk, False


def _setup(monkeypatch):
    monkeypatch.setattr(recorder, "is_speech", lambda c: np.abs(c).mean() > 100)
    monkeypatch.setattr(config, "SILENCE_SECONDS", 0.6)
    monkeypatch.setattr(config, "MAX_RECORD_SECONDS", 10)
    monkeypatch.setattr(config, "SPEAKER_DROP", 0.35)


def test_background_chatter_does_not_keep_recording(monkeypatch):
    _setup(monkeypatch)
    you, chatter = [3000] * 20, [600] * 200  # 1.6 s of you, then quieter voices forever
    stream = FakeStream(you + chatter)
    audio = recorder.record_until_silence(stream)
    seconds = len(audio) / config.SAMPLE_RATE
    assert seconds < 2.6, seconds  # stopped ~0.6 s after you did, not at the 10 s limit


def test_your_own_quieter_words_still_count(monkeypatch):
    _setup(monkeypatch)
    stream = FakeStream([3000] * 10 + [1500] * 10 + [3000] * 5)  # you trail off a bit mid-sentence
    audio = recorder.record_until_silence(stream)
    assert len(audio) / config.SAMPLE_RATE > 1.9


def test_recording_has_a_hard_limit(monkeypatch):
    _setup(monkeypatch)
    stream = FakeStream([3000] * 1000)
    audio = recorder.record_until_silence(stream)
    assert len(audio) / config.SAMPLE_RATE <= 10.1
