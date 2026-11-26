"""Conversations: after the wake word, Jarvis keeps listening (no wake word)
until he's quiet for a while or says he's done."""
import contextlib

import numpy as np
import pytest

import config
import main
import ui_events


class FakeStream:
    def start(self):
        pass

    def stop(self):
        pass


def _run(monkeypatch, heard, ignore=()):
    """heard: what each recording turns out to be (None = silence, '' = mumble).
    Returns (calls to respond as (text, followup), what Jarvis said, recordings)."""
    monkeypatch.setattr(config, "MODE", "enter")
    monkeypatch.setattr(config, "AUTO_CALIBRATE", False)
    monkeypatch.setattr(config, "FOLLOWUP_SECONDS", 12)
    monkeypatch.setattr(main, "open_stream", lambda: contextlib.nullcontext(FakeStream()))
    monkeypatch.setattr(main, "chime", lambda s: 0)
    triggers = iter([("talk", None), ("text", "shut down")])
    monkeypatch.setattr(main, "wait_for_trigger", lambda s: next(triggers))
    clips = iter(heard)
    recorded = []

    def record(stream, timeout=None, ignore_seconds=0):
        recorded.append(timeout)
        said = next(clips)
        return np.array([], dtype=np.float32) if said is None else np.full(len(recorded), 0.1, np.float32)

    monkeypatch.setattr(main, "record_until_silence", record)
    monkeypatch.setattr(main, "transcribe", lambda audio: heard[len(audio) - 1])
    calls, spoken = [], []

    def respond(text, t_heard=None, stream=None, followup=False, note=""):
        calls.append((text, followup))
        main.last_ignored = text in ignore
        main.asked_question = False
        return False
    monkeypatch.setattr(main, "respond", respond)
    monkeypatch.setattr(main, "say", spoken.append)
    monkeypatch.setattr(main, "speak", spoken.append)
    monkeypatch.setattr(main.ducking, "duck", lambda: None)
    monkeypatch.setattr(main.ducking, "restore", lambda: None)
    main.asked_question = False
    main.main()
    return calls, spoken, recorded


def test_keeps_listening_until_he_says_thanks(monkeypatch):
    calls, spoken, recorded = _run(monkeypatch, [
        "what's the weather", "and tomorrow?", "ok", "", "what about saturday", "thanks jarvis"])
    assert calls == [("what's the weather", False), ("and tomorrow?", True), ("what about saturday", True)]
    assert "Anytime, sir." in spoken
    assert all(t and t > 5 for t in recorded[1:])   # follow-ups wait more than a moment


def test_quiet_ends_the_conversation(monkeypatch):
    calls, spoken, _ = _run(monkeypatch, ["set a timer for 5 minutes", None])
    assert calls == [("set a timer for 5 minutes", False)]
    assert not any("sir" in s and "Anytime" in s for s in spoken)


def test_chatter_he_ignored_doesnt_end_it(monkeypatch):
    calls, _, _ = _run(monkeypatch, ["open spotify", "tell mom I'm busy", "play my study playlist", None],
                       ignore={"tell mom I'm busy"})
    assert [c[0] for c in calls] == ["open spotify", "tell mom I'm busy", "play my study playlist"]


def test_mumble_after_wake_word_asks_again(monkeypatch):
    calls, spoken, _ = _run(monkeypatch, ["", "what time is it", None])
    assert "Sorry, sir, I didn't catch that." in spoken
    assert calls == [("what time is it", True)]


@pytest.mark.parametrize("said, expected", [
    ("thanks", "close"), ("thank you jarvis", "close"), ("okay that's all for now", "close"),
    ("never mind", "close"), ("bye", "close"), ("that's it thanks", "close"),
    ("ok", "quiet"), ("cool", "quiet"), ("jarvis", "name"),
    ("thanks can you also email sam", "answer"), ("what's next", "answer"), ("no", "quiet"),
])
def test_followup_action(said, expected):
    main.asked_question = False
    assert main.followup_action(said, answering=False) == expected


def test_answers_to_his_question_go_through():
    assert main.followup_action("no", answering=True) == "answer"
    assert main.followup_action("thanks", answering=True) == "answer"


def test_old_saved_window_moves_to_new_default(monkeypatch, tmp_path):
    from brain import memory, settings
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "FOLLOWUP_SECONDS", 12)
    memory._write(settings.FILE, {"followup_seconds": 5})
    settings.apply()
    assert config.FOLLOWUP_SECONDS == 12
    memory._write(settings.FILE, dict(memory._read(settings.FILE, {}), followup_seconds=5))
    settings.apply()                     # he chose 5 himself after that: kept
    assert config.FOLLOWUP_SECONDS == 5
