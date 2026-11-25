import threading
import time

import config
import main


class FakeStream:
    def __init__(self):
        self.active = False

    def start(self):
        assert not self.active, "started twice"
        self.active = True

    def stop(self):
        self.active = False


def fake_think(n):
    def think_stream(text):
        for i in range(n):
            yield f"Sentence {i}."
    return think_stream


def setup(monkeypatch, played, n=10):
    monkeypatch.setattr(config, "MODE", "wake")
    monkeypatch.setattr(config, "BARGE_IN", True)
    monkeypatch.setattr(main, "think_stream", fake_think(n))
    monkeypatch.setattr(main.tts, "synthesize", lambda s: (s, 1))
    monkeypatch.setattr(main.tts, "play", lambda clip: (played.append(clip[0]), time.sleep(0.05)))


def test_interrupt_stops_speaking(monkeypatch):
    played = []
    setup(monkeypatch, played)

    def watch(stream, stop_event, on_wake):
        time.sleep(0.12)  # "Hey Jarvis" after a couple of sentences
        on_wake()

    monkeypatch.setattr(main, "watch_for_interrupt", watch)
    stream = FakeStream()
    assert main.respond("talk", stream=stream) is True
    assert 0 < len(played) < 10
    assert not stream.active  # mic left stopped, as main() expects


def test_no_interrupt_plays_everything(monkeypatch):
    played = []
    setup(monkeypatch, played, n=3)

    def watch(stream, stop_event, on_wake):
        stop_event.wait()

    monkeypatch.setattr(main, "watch_for_interrupt", watch)
    stream = FakeStream()
    assert main.respond("talk", stream=stream) is False
    assert played == ["Sentence 0.", "Sentence 1.", "Sentence 2."]
    assert not stream.active


def test_barge_in_off(monkeypatch):
    played = []
    setup(monkeypatch, played, n=2)
    monkeypatch.setattr(config, "BARGE_IN", False)
    monkeypatch.setattr(main, "watch_for_interrupt", lambda *a: (_ for _ in ()).throw(AssertionError))
    stream = FakeStream()
    assert main.respond("talk", stream=stream) is False
    assert played == ["Sentence 0.", "Sentence 1."]
    assert not stream.active
    assert threading.active_count() < 20


def test_text_shows_when_its_voice_starts(monkeypatch):
    log = []
    setup(monkeypatch, [], n=2)
    monkeypatch.setattr(main.tts, "play", lambda clip: log.append(("play", clip[0])))
    monkeypatch.setattr(main.ui_events, "emit",
                        lambda kind, text: log.append(("show", text)) if kind == "jarvis" else None)
    monkeypatch.setattr(config, "MODE", "enter")
    main.respond("talk")
    assert log == [("show", "Sentence 0."), ("play", "Sentence 0."),
                   ("show", "Sentence 1."), ("play", "Sentence 1.")]
