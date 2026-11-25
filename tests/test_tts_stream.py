"""Streaming voice: audio starts before the whole sentence has downloaded."""
import threading

import numpy as np
import pytest

from audio import tts


class FakeFish:
    status_code = 200
    text = ""

    def __init__(self, parts, gate=None):
        self.parts, self.gate = parts, gate

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=4096):
        for i, p in enumerate(self.parts):
            if i == 1 and self.gate:
                self.gate.wait(2)   # hold back the rest of the audio
            yield p


class FakeOut:
    written = []

    def __init__(self, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def write(self, data):
        FakeOut.written.append(data.copy())


@pytest.fixture
def speakers(monkeypatch):
    FakeOut.written = []
    monkeypatch.setattr(tts.sd, "OutputStream", FakeOut, raising=False)
    monkeypatch.setattr(tts, "_fish_ok", True)
    return FakeOut.written


def test_plays_first_audio_before_the_rest_arrives(monkeypatch, speakers):
    gate = threading.Event()
    first = np.arange(100, dtype=np.int16).tobytes()
    rest = np.arange(100, 200, dtype=np.int16).tobytes()
    # Odd byte split checks half-samples are carried over.
    monkeypatch.setattr(tts, "_fish_request", lambda text, stream: FakeFish([first + rest[:1], rest[1:]], gate))
    clip = tts.synthesize("Hello there.")
    assert isinstance(clip, tts.StreamClip)
    played_first = threading.Event()

    def watch():
        while not speakers:
            pass
        played_first.set()
        gate.set()
    threading.Thread(target=watch, daemon=True).start()
    tts.play(clip)
    assert played_first.is_set()
    assert np.concatenate(speakers).ravel().tolist() == list(range(200))


def test_falls_back_to_piper_when_fish_fails(monkeypatch, speakers):
    def broken(text, stream):
        raise ConnectionError("offline")
    monkeypatch.setattr(tts, "_fish_request", broken)
    monkeypatch.setattr(tts, "_synth_piper", lambda text: (np.ones(50, dtype=np.int16), 22050))
    clip = tts.synthesize("Hello.")
    tts.play(clip)
    assert clip.rate == 22050
    assert sum(len(w) for w in speakers) == 50


def test_system_voice_when_nothing_works(monkeypatch, speakers):
    monkeypatch.setattr(tts, "_fish_request", lambda t, stream: (_ for _ in ()).throw(OSError("x")))
    monkeypatch.setattr(tts, "_synth_piper", lambda text: None)
    said = []
    monkeypatch.setattr(tts, "speak_system", said.append)
    tts.play(tts.synthesize("Hello."))
    assert said == ["Hello."]


def test_stop_cuts_off_a_stream(monkeypatch, speakers):
    data = np.zeros(44100, dtype=np.int16).tobytes()
    monkeypatch.setattr(tts, "_fish_request", lambda t, stream: FakeFish([data, data]))
    clip = tts.synthesize("Long sentence.")
    clip.done.wait(2)
    orig = FakeOut.write

    def write(self, d):
        orig(self, d)
        if len(FakeOut.written) == 3:
            tts.stop()
    monkeypatch.setattr(FakeOut, "write", write)
    tts.play(clip)
    assert len(speakers) == 3
