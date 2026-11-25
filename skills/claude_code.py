"""Hand coding jobs to Claude Code by voice: "Jarvis, ask Claude Code to fix the timer bug".

Idea from OpenLive (github.com/katipally/openlive, Apache-2.0), which
voice-drives coding agents. Runs the `claude` command line in print mode
(`claude -p`) inside one of the folders in CLAUDE_CODE_PROJECTS, in the
background. When it finishes Jarvis says a short summary, and the full answer
goes to Telegram if the bot is set up.

Like email replies, a task only starts after Jarvis has read it back and you
said yes in a later turn. Needs Claude Code installed and signed in
(docs.claude.com/claude-code)."""
import json
import os
import shutil
import subprocess
import threading
import time

import config
import skills
from skills import timers

PROJECTS = getattr(config, "CLAUDE_CODE_PROJECTS", {})
PERMISSION_MODE = getattr(config, "CLAUDE_CODE_PERMISSION_MODE", "acceptEdits")
TIMEOUT_MINUTES = getattr(config, "CLAUDE_CODE_TIMEOUT_MINUTES", 30)
DRAFT_MINUTES = 10

_draft = None  # (project, folder, task, continue, turn made in, time made)
_running = {}  # project -> start time


def _folder(project):
    name = (project or "").strip().lower()
    for key, path in PROJECTS.items():
        if key.lower() == name:
            return key, path
    if len(PROJECTS) == 1 and not name:
        return next(iter(PROJECTS.items()))
    return None, None


def _summary(text, sentences=2):
    parts = text.replace("\n", " ").split(". ")
    return ". ".join(parts[:sentences]).strip()[:400]


def _run(project, folder, task, cont):
    exe = shutil.which("claude") or "claude"
    cmd = [exe, "-p", task, "--output-format", "json", "--permission-mode", PERMISSION_MODE]
    if cont:
        cmd.append("--continue")
    t0 = time.monotonic()
    try:
        out = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, encoding="utf-8",
                             timeout=TIMEOUT_MINUTES * 60)
        try:
            data = json.loads(out.stdout)
            result = data.get("result") or out.stderr or "It finished without a reply."
            failed = data.get("is_error", False)
        except ValueError:
            result, failed = (out.stdout or out.stderr or "No output.").strip(), out.returncode != 0
    except subprocess.TimeoutExpired:
        result, failed = f"It was still going after {TIMEOUT_MINUTES} minutes, so I stopped it.", True
    except Exception as e:
        result, failed = f"Couldn't run Claude Code: {e}", True
    finally:
        _running.pop(project, None)
    minutes = (time.monotonic() - t0) / 60
    print(f"[claude code] {project} finished in {minutes:.1f} min: {result[:200]}")
    sent = False
    try:
        import telegram_bot
        sent = telegram_bot.notify(f"Claude Code ({project}): {task}\n\n{result}")
    except Exception as e:
        print(f"[claude code] couldn't send to Telegram: {e}")
    head = "Sir, Claude Code ran into trouble" if failed else "Sir, Claude Code has finished"
    timers.announce(f"{head} on {project}. {_summary(result)}"
                    + (" The full reply is on your phone." if sent else ""))


def plan_task(a):
    global _draft
    if not PROJECTS:
        return ("No projects are set up. Add folders to CLAUDE_CODE_PROJECTS in config.py, "
                'e.g. {"jarvis": r"C:\\Users\\me\\Jarvis"}.')
    if not shutil.which("claude"):
        return "Claude Code isn't installed on this PC (the 'claude' command wasn't found)."
    project, folder = _folder(a.get("project"))
    if not folder:
        return f"Which project? Known ones: {', '.join(PROJECTS)}."
    if not os.path.isdir(folder):
        return f"The folder for {project} doesn't exist: {folder}"
    task = (a.get("task") or "").strip()
    if not task:
        return "No task given."
    _draft = (project, folder, task, bool(a.get("continue_last")), skills.turn, time.monotonic())
    return (f"Ready to ask Claude Code, in {project}: \"{task}\". Read the task back to him in a few "
            "words and ask whether to start. Only call start_claude_code_task after he says yes.")


def start_task(a):
    global _draft
    if _draft is None:
        return "There's no task waiting. Use plan_claude_code_task first."
    project, folder, task, cont, made_in, made_at = _draft
    if skills.turn <= made_in:
        return "Wait for him to say yes first: read the task back and ask."
    if time.monotonic() - made_at > DRAFT_MINUTES * 60:
        _draft = None
        return "That task was planned too long ago; plan it again."
    if project in _running:
        return f"Claude Code is already working on {project}."
    _draft = None
    _running[project] = time.monotonic()
    threading.Thread(target=_run, args=(project, folder, task, cont), daemon=True).start()
    return f"Started Claude Code on {project}. Tell him you'll let him know when it's done."


def status(a):
    if not _running:
        return "Claude Code isn't working on anything."
    return "; ".join(f"{p}: running for {(time.monotonic() - t) / 60:.0f} min" for p, t in _running.items())


SKILLS = [
    {
        "name": "plan_claude_code_task",
        "description": (
            "Prepare a coding job for Claude Code (an AI coding agent) in one of his project folders, "
            "e.g. 'ask Claude Code to fix the timer bug in Jarvis'. Step 1 of 2: this only prepares it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "project name, e.g. 'jarvis'"},
                "task": {"type": "string", "description": "the instruction for Claude Code, in full sentences"},
                "continue_last": {"type": "boolean", "description": "carry on from the last Claude Code session there"},
            },
            "required": ["task"],
        },
        "run": plan_task,
    },
    {
        "name": "start_claude_code_task",
        "description": "Step 2 of 2: start the prepared Claude Code job, only after he said yes in his latest message.",
        "parameters": {"type": "object", "properties": {}},
        "run": start_task,
    },
    {
        "name": "claude_code_status",
        "description": "Whether Claude Code is still working on a job he gave it.",
        "parameters": {"type": "object", "properties": {}},
        "run": status,
    },
]
