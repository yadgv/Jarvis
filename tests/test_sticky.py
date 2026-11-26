"""Reminders for when he's back at the PC."""
import pytest

import config
from skills import sticky, timers


@pytest.fixture
def mem(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    said = []
    monkeypatch.setattr(timers, "announce", said.append)
    return said


def test_add_list_and_deliver(mem):
    assert "Noted" in sticky.remind_when_back({"text": "email the prof"})
    sticky.remind_when_back({"text": "charge the laptop"})
    assert "email the prof; charge the laptop" in sticky.remind_when_back({"action": "list"})
    assert sticky.deliver()
    assert "email the prof; charge the laptop" in mem[0] and mem[0].startswith("Welcome back")
    assert not sticky.deliver()                       # said once, then gone
    assert "No notes" in sticky.remind_when_back({"action": "list"})


def test_one_note_reads_naturally_and_clear(mem):
    sticky.remind_when_back({"text": "Call mom."})
    sticky.deliver()
    assert mem == ["Welcome back, sir. You asked me to remind you: Call mom."]
    sticky.remind_when_back({"text": "x"})
    assert "Cleared 1 note" in sticky.remind_when_back({"action": "clear"})
    assert "What should I" in sticky.remind_when_back({})


def test_watch_says_them_when_he_comes_back(mem, monkeypatch):
    sticky.remind_when_back({"text": "stretch"})
    idles = iter([400.0, 600.0, 1.0])
    monkeypatch.setattr(sticky, "idle_seconds", lambda: next(idles))

    def stop(s):
        if not mem:
            return
        raise SystemExit
    monkeypatch.setattr(sticky.time, "sleep", stop)
    with pytest.raises(SystemExit):
        sticky._watch()
    assert "stretch" in mem[0]


def test_startup_says_leftovers(mem, monkeypatch):
    monkeypatch.setattr(sticky.sys, "platform", "linux")
    sticky.remind_when_back({"text": "water the plant"})
    sticky.start()
    assert "water the plant" in mem[0]
