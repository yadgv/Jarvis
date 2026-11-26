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


def test_builds_a_new_app_and_opens_it(monkeypatch, tmp_path, private_files):
    setup(monkeypatch, tmp_path)
    apps_file = tmp_path / "apps.json"
    monkeypatch.setattr(claude_code, "_apps_path", lambda: str(apps_file))
    out = claude_code.plan_app({"what": "a pomodoro timer", "name": "pomodoro"})
    assert "Ready to have Claude Code build \"pomodoro\"" in out and "after he says yes" in out
    assert "Wait for him" in claude_code.start_task({})
    monkeypatch.setattr(skills, "turn", skills.turn + 1)
    done, said, calls, opened = threading.Event(), [], [], []
    monkeypatch.setattr(timers, "announce", lambda t: (said.append(t), done.set()))
    monkeypatch.setattr(telegram_bot, "notify", lambda t: False)

    def fake_run(cmd, cwd, **k):
        calls.append((cmd, cwd))
        with open(f"{cwd}/index.html", "w") as f:
            f.write("<h1>Pomodoro</h1>")
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": "Built a pomodoro timer. Open index.html."}), "")
    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    monkeypatch.setattr(claude_code, "_open_app", lambda folder: opened.append(folder) or "index.html")
    assert "Started" in claude_code.start_task({})
    assert done.wait(5)
    cmd, cwd = calls[0]
    folder = str(private_files / "Documents" / "Jarvis apps" / "pomodoro")
    assert cwd == folder and opened == [folder]
    task = cmd[cmd.index("-p") + 1]
    assert "pomodoro timer" in task and "single index.html" in task and "outside this folder" in task
    assert "opened it" in said[0]
    # It's a project now, so he can ask for changes, even after a restart.
    assert claude_code.PROJECTS["pomodoro"] == folder
    assert json.loads(apps_file.read_text()) == {"pomodoro": folder}
    monkeypatch.setattr(claude_code, "PROJECTS", {})
    claude_code._load_apps()
    assert claude_code.PROJECTS == {"pomodoro": folder}
    assert "already an app called pomodoro" in claude_code.plan_app({"what": "another", "name": "Pomodoro"})


def test_app_without_claude_code_says_how_to_install(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setattr(claude_code.shutil, "which", lambda n: None)
    out = claude_code.plan_app({"what": "a game"})
    assert "install.ps1" in out and "sign in" in out


def test_app_requests_get_the_app_tools_and_yes_starts_it():
    for ask in ("build me a pomodoro timer app", "make me a little web page for my schedule",
                "add a dark mode to my pomodoro app", "code a simple snake game"):
        assert "plan_new_app" in skills.pick_tools(ask), ask
    assert skills.FOLLOW_UPS["plan_new_app"] == ("start_claude_code_task",)
