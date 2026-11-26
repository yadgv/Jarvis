"""Study mode: quizzes from notes, Pomodoro and focus nudges."""
import json
import time

import pytest

import config
import skills
from skills import study, timers


@pytest.fixture
def mem(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    study._quiz.update(cards=[], i=0, right=0, wrong=[])
    return tmp_path


CARDS = [{"q": "What is the first law?", "a": "Energy is conserved"}, {"q": "Units of entropy?", "a": "J/K"}]


def test_quiz_from_notes_one_question_at_a_time(mem, monkeypatch):
    from brain import llm
    from skills import files
    monkeypatch.setattr(files, "file_text", lambda name: ("Entropy... first law...", None))
    asked = []
    monkeypatch.setattr(llm, "complete", lambda system, user, **k: asked.append(user) or json.dumps(CARDS))
    out = study.quiz_me({"file": "thermo notes", "count": 2})
    assert "Question 1 of 2: What is the first law?" in out and "Expected answer" in out
    assert "Entropy" in asked[0]
    out = study.quiz_next({"correct": True})
    assert "Question 2 of 2" in out
    out = study.quiz_next({"correct": False})
    assert "1 out of 2" in out and "saved" in out
    out = study.quiz_me({"missed": True})
    assert "Units of entropy?" in out and "1 questions" in out or "1 question" in out


def test_quiz_needs_a_source(mem):
    assert "which notes" in study.quiz_me({})
    assert "No quiz is running" in study.quiz_next({"correct": True})
    assert "no missed questions" in study.quiz_me({"missed": True})


def test_parse_rejects_junk():
    with pytest.raises(ValueError):
        study._parse("Sure! Here are some questions.")
    assert study._parse('ok [{"q": "x?", "a": "y"}, {"bad": 1}]') == [{"q": "x?", "a": "y"}]


def test_distraction_spotting():
    assert study.distracted("Funny cats - YouTube - Google Chrome") == "YouTube"
    assert study.distracted("Thermo notes.docx - Word") == ""
    assert study.distracted("Jarvis whiteboard") == ""


def test_pomodoro_rounds_and_nudges(monkeypatch):
    said = []
    monkeypatch.setattr(timers, "announce", said.append)
    monkeypatch.setattr(study, "CHECK_EVERY", 0.01)
    monkeypatch.setattr(study, "NUDGE_EVERY", 999)
    monkeypatch.setattr(study, "_foreground_title", lambda: "Lofi - YouTube")
    out = study.pomodoro({"minutes": 0.002, "break_minutes": 0.001, "rounds": 2})
    assert "2 rounds" in out
    study._pom.thread.join(3)
    assert any("YouTube" in s and "Back to work" in s for s in said)
    assert sum("Back to work" in s for s in said) == 1          # not more often than NUDGE_EVERY
    assert any("Take a" in s for s in said) and any("Break's over" in s for s in said)
    assert "whole session" in said[-1]


def test_pomodoro_stop_and_status(monkeypatch):
    monkeypatch.setattr(timers, "announce", lambda s: None)
    study.pomodoro({"minutes": 30, "total_minutes": 120})
    assert study._pom.rounds == 3
    assert "Round 1 of 3, focus time, 30 minutes left" in study.pomodoro({"action": "status"})
    assert "stopped" in study.pomodoro({"action": "stop"})
    assert "No study session" in study.pomodoro({"action": "status"})


def test_study_words_bring_the_tools():
    assert {"quiz_me", "pomodoro"} <= skills.pick_tools("quiz me on my thermo notes", limit=3)
