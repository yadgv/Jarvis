import pytest

import config

config.MODE = "enter"  # don't load the wake-word model
import main  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("Okay, shut down", True),
    ("shut down please", True),
    ("Jarvis, power off", True),
    ("ok you can go to sleep now", True),
    ("Goodbye Jarvis", True),
    ("don't shut down the PC", False),
    ("can I shut down", False),
    ("shut down the computer", False),
    ("okay", False),
])
def test_exit_phrases(text, expected):
    assert main.is_exit(main.normalize(text)) is expected


@pytest.mark.parametrize("text,expected", [
    ("I understand.", True),
    ("Okay.", True),
    ("Thanks, Jarvis.", True),
    ("Got it", True),
    ("What about tomorrow?", False),
    ("I understand the plan but what time is it", False),
])
def test_acknowledgements(text, expected):
    assert main.is_acknowledgement(main.normalize(text)) is expected


def test_ignored_followup_says_nothing(monkeypatch):
    shown, played = [], []
    monkeypatch.setattr(main, "think_stream", lambda text, followup=False: iter(()))
    monkeypatch.setattr(main.tts, "synthesize", lambda s: (s, 1))
    monkeypatch.setattr(main.tts, "play", lambda clip: played.append(clip[0]))
    monkeypatch.setattr(main.ui_events, "emit", lambda k, t: shown.append(t) if k == "jarvis" else None)
    main.respond("so anyway he said", followup=True)
    assert main.last_ignored and not played and not shown
    # A normal (woken) turn with no reply still apologises.
    main.respond("hello")
    assert not main.last_ignored and played


def test_question_marks_answer_window(monkeypatch):
    """A bare "yes" after "Shall I send it?" is an answer, not the end of the chat."""
    monkeypatch.setattr(main.tts, "synthesize", lambda s: (s, 1))
    monkeypatch.setattr(main.tts, "play", lambda clip: None)
    monkeypatch.setattr(main.ui_events, "emit", lambda k, t: None)
    monkeypatch.setattr(main, "think_stream", lambda text, **k: iter(["Here's the draft.", "Shall I send it?"]))
    main.respond("reply to Sam")
    assert main.asked_question and "yes" in main.ANSWERS
    monkeypatch.setattr(main, "think_stream", lambda text, **k: iter(["Sent, sir."]))
    main.respond("yes")
    assert not main.asked_question


@pytest.mark.parametrize("text,expected", [
    ("Jarvis.", True), ("Hey Jarvis", True), ("Jarvis?", True),
    ("thanks", False), ("Jarvis play Drake", False), ("sir", False),
])
def test_just_his_name_means_listen(text, expected):
    """A bare "Jarvis" in the follow-up window starts listening, not ends the chat."""
    assert main.is_just_name(main.normalize(text)) is expected
