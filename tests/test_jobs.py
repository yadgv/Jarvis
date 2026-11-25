"""Standing jobs and watchers."""
from datetime import datetime

import pytest

import telegram_bot
from brain import llm, memory
from skills import jobs, timers


@pytest.fixture
def store(monkeypatch):
    data = {}
    monkeypatch.setattr(memory, "_read", lambda name, default: data.get(name, default))
    monkeypatch.setattr(memory, "_write", lambda name, value: data.__setitem__(name, value))
    monkeypatch.setattr(jobs, "_running", set())
    return data


def test_next_run_weekdays():
    job = {"time": "08:00", "days": jobs.DAYS[:5]}
    fri_evening = datetime(2026, 11, 27, 20, 0)  # a Friday
    assert jobs.next_run(job, fri_evening) == datetime(2026, 11, 30, 8, 0)  # Monday
    assert jobs.next_run(job, datetime(2026, 11, 30, 7, 0)) == datetime(2026, 11, 30, 8, 0)


def test_schedule_list_cancel(store):
    assert "saved" in jobs.schedule_job({"task": "weather and first meeting", "time": "08:00", "days": "weekdays"})
    assert "weekdays at 08:00" in jobs.list_jobs({})
    assert "HH:MM" in jobs.schedule_job({"task": "x", "time": "25:99"})
    assert "Cancelled 1" in jobs.cancel_job({"id_or_words": "weather"})


def test_watch_speaks_only_when_new(store, monkeypatch):
    replies = iter(["Mom emailed about dinner.", "Mom emailed about dinner.", "[nothing]", "Mom emailed again."])
    monkeypatch.setattr(llm, "run_job", lambda prompt, exclude: next(replies))
    said = []
    monkeypatch.setattr(timers, "announce", said.append)
    jobs.schedule_job({"task": "tell me when Mom emails", "every_minutes": 15, "only_when_new": True})
    job = store["jobs.json"][0]
    for _ in range(4):
        jobs.run_one(dict(store["jobs.json"][0]))
    assert said == ["Mom emailed about dinner.", "Mom emailed again."]
    assert job["watch"]


def test_jobs_only_get_safe_tools(store, monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "run_job", lambda prompt, exclude: seen.setdefault("ex", exclude) and "ok")
    monkeypatch.setattr(timers, "announce", lambda t: None)
    jobs.run_one({"id": "a", "task": "x", "deliver": "speak"})
    assert "reply_email" in seen["ex"] and "use_computer" in seen["ex"]
    assert "get_weather" not in seen["ex"]


def test_phone_delivery_falls_back_to_speaking(store, monkeypatch):
    monkeypatch.setattr(llm, "run_job", lambda p, e: "Report.")
    monkeypatch.setattr(telegram_bot, "notify", lambda t: False)
    said = []
    monkeypatch.setattr(timers, "announce", said.append)
    jobs.run_one({"id": "b", "task": "x", "deliver": "phone"})
    assert said == ["Report."]


def test_tick_runs_due_jobs_once(store, monkeypatch):
    ran = []
    monkeypatch.setattr(jobs, "run_one", ran.append)
    monkeypatch.setattr(jobs.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda s: target(*args)})())
    jobs.schedule_job({"task": "x", "every_minutes": 10})
    store["jobs.json"][0]["next"] = "2000-01-01T00:00"
    jobs._tick()
    jobs._tick()
    assert len(ran) == 1


def test_run_job_uses_no_history(monkeypatch):
    seen = {}

    def fake_turn(text, system, said, used, exclude=(), history=None):
        seen["history"], seen["exclude"] = history, exclude
        said.append("All clear.")
        yield "All clear."
    monkeypatch.setattr(llm, "_claude_turn", fake_turn)
    monkeypatch.setattr(llm, "_use_claude", lambda: True)
    assert llm.run_job("check", ["reply_email"]) == "All clear."
    assert seen["history"] == [] and "shut_down" in seen["exclude"]
