from datetime import datetime, timedelta

import pytest

import config
import main
from skills import briefing, calendar_events, news, reminders, weather


@pytest.fixture(autouse=True)
def mem(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))


@pytest.mark.parametrize("text,expected", [
    ("Good morning, Jarvis!", True),
    ("Hey Jarvis, good morning", True),
    ("hello", True),
    ("Morning sir", True),
    ("What's the weather?", False),
    ("good morning what's on today", False),
])
def test_greetings(text, expected):
    now = datetime.now().replace(hour=8)
    assert briefing.is_first_hello(main.normalize(text), now) is expected


def test_only_once_a_day_and_not_at_night():
    morning = datetime.now().replace(hour=8)
    assert not briefing.is_first_hello("hello", morning.replace(hour=2))
    briefing.mark_briefed(morning.date())
    assert not briefing.is_first_hello("hello", morning)
    assert briefing.is_first_hello("hello", morning + timedelta(days=1))


def test_briefing_collects_everything(monkeypatch):
    monkeypatch.setattr(weather, "get_weather", lambda a: "Courtice. Now: 3°C, clear")
    monkeypatch.setattr(calendar_events, "get_events", lambda a: "- 3 PM to 4 PM: Dentist")
    monkeypatch.setattr(news, "get_news", lambda a: "- Leafs win (TSN)")
    reminders.set_reminder({"text": "call mum", "in_minutes": 1})
    reminders.set_reminder({"text": "next week thing", "when": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")})
    out = briefing.daily_briefing()
    assert "3°C" in out and "Dentist" in out and "Leafs" in out and "call mum" in out
    assert "next week thing" not in out
    assert not briefing.is_first_hello("hello", datetime.now().replace(hour=9))


def test_briefing_survives_a_broken_part(monkeypatch):
    def boom(a):
        raise RuntimeError("offline")
    monkeypatch.setattr(weather, "get_weather", boom)
    monkeypatch.setattr(calendar_events, "get_events", lambda a: "No events")
    monkeypatch.setattr(news, "get_news", lambda a: "- x")
    out = briefing.daily_briefing()
    assert "Weather: unavailable (offline)" in out and "No events" in out
