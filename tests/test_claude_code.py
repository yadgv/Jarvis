"""Claude Code by voice: read back first, start only after a yes, report when done."""
import json
import subprocess
import threading

import skills
import telegram_bot
from skills import claude_code, timers


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_code, "PROJECTS", {"jarvis": str(tmp_path)})
    monkeypatch.setattr(claude_code.shutil, "which", lambda n: "/usr/bin/claude")
    monkeypatch.setattr(claude_code, "_draft", None)
    monkeypatch.setattr(claude_code, "_running", {})


def test_needs_a_yes_in_a_later_turn(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    assert "Ready" in claude_code.plan_task({"project": "Jarvis", "task": "Fix the timer bug."})
    assert "Wait for him" in claude_code.start_task({})
    monkeypatch.setattr(skills, "turn", skills.turn + 1)

    done = threading.Event()
    said = []
    monkeypatch.setattr(timers, "announce", lambda t: (said.append(t), done.set()))
    monkeypatch.setattr(telegram_bot, "notify", lambda t: True)
    calls = []

    def fake_run(cmd, cwd, **k):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": "Fixed it. Tests pass. Details."}), "")
    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    assert "Started" in claude_code.start_task({})
    assert done.wait(5)
    assert calls[0][1] == str(tmp_path) and "-p" in calls[0][0]
    assert "finished on jarvis" in said[0] and "Fixed it" in said[0] and "phone" in said[0]


def test_unknown_project_and_missing_cli(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setattr(claude_code, "PROJECTS", {"a": str(tmp_path), "b": str(tmp_path)})
    assert "Which project" in claude_code.plan_task({"project": "zzz", "task": "x"})
    monkeypatch.setattr(claude_code.shutil, "which", lambda n: None)
    assert "isn't installed" in claude_code.plan_task({"project": "a", "task": "x"})
