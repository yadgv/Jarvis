"""Hand coding jobs to Claude Code by voice: "Jarvis, ask Claude Code to fix the timer bug".

Idea from OpenLive (github.com/katipally/openlive, Apache-2.0), which
voice-drives coding agents. Runs the `claude` command line in print mode
(`claude -p`) inside one of the folders in CLAUDE_CODE_PROJECTS, in the
background. When it finishes Jarvis says a short summary, and the full answer
goes to Telegram if the bot is set up.

Like email replies, a task only starts after Jarvis has read it back and you
said yes in a later turn. Needs Claude Code installed and signed in
(docs.claude.com/claude-code).

"Build me a pomodoro timer app" makes a new folder in Documents/Jarvis apps
and has Claude Code build a small app or web page there (one index.html when
it can, so it just opens in the browser). When it's done Jarvis opens it, and
the folder becomes a project, so "add a dark mode to my pomodoro app" works
later."""
import json
import os
import re
import shutil
import subprocess
import threading
import time

import config
import skills
from skills import timers

PROJECTS = dict(getattr(config, "CLAUDE_CODE_PROJECTS", {}))
APPS_FOLDER = "Jarvis apps"
INSTALL = ("Claude Code isn't installed on this PC (the 'claude' command wasn't found). Tell him to install it: "
           "in PowerShell run  irm https://claude.ai/install.ps1 | iex  then run  claude  once to sign in.")
APP_TASK = (
    "Build this for me in this empty folder: {what}.\n"
    "- Keep it small and self-contained. Unless I asked for something else, make it a single index.html "
    "with the CSS and JavaScript inside, no build step and no internet needed, so it opens by double-clicking.\n"
    "- If it has to be Python, use only the standard library (tkinter for windows) and name the file main.py.\n"
    "- Make it look clean and modern, and work with mouse and keyboard.\n"
    "- Add a short README.md saying what it does and how to open it.\n"
    "- Don't install anything and don't touch files outside this folder.\n"
    "When you're done, reply with two sentences: what you built and how to use it."
)
PERMISSION_MODE = getattr(config, "CLAUDE_CODE_PERMISSION_MODE", "acceptEdits")
TIMEOUT_MINUTES = getattr(config, "CLAUDE_CODE_TIMEOUT_MINUTES", 30)
DRAFT_MINUTES = 10

_draft = None  # (project, folder, task, continue, turn made in, time made)
_running = {}  # project -> start time


def _apps_path():
    return os.path.join(config.MEMORY_DIR, "claude_code_apps.json")


def _load_apps():
    """Apps Claude Code built before, so he can ask for changes later."""
    try:
        with open(_apps_path(), encoding="utf-8") as f:
            apps = json.load(f)
    except (OSError, ValueError):
        return
    for name, path in (apps.items() if isinstance(apps, dict) else []):
        if isinstance(path, str) and os.path.isdir(path):
            PROJECTS.setdefault(name, path)


def _remember_app(name, path):
    try:
        with open(_apps_path(), encoding="utf-8") as f:
            apps = json.load(f)
    except (OSError, ValueError):
        apps = {}
    apps[name] = path
    os.makedirs(os.path.dirname(_apps_path()), exist_ok=True)
    with open(_apps_path(), "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=1)
    PROJECTS[name] = path


def _open_app(folder):
    """Open what was built: index.html in the browser, else the folder."""
    for name in ("index.html", "main.py"):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            break
    else:
        path = folder
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)
        elif path.endswith(".html"):
            import webbrowser
            webbrowser.open("file://" + path)
        return os.path.basename(path)
    except OSError as e:
        print(f"[claude code] couldn't open {path}: {e}")
        return None


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


def _run(project, folder, task, cont, new_app=False):
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
    opened = None
    if new_app and not failed:
        _remember_app(project, folder)
        opened = _open_app(folder)
    timers.announce(f"{head} on {project}. {_summary(result)}"
                    + (" I've opened it for you." if opened else "")
                    + (" The full reply is on your phone." if sent else ""))


_load_apps()


def plan_task(a):
    global _draft
    if not PROJECTS:
        return ("No projects are set up. Add folders to CLAUDE_CODE_PROJECTS in config.py, "
                'e.g. {"jarvis": r"C:\\Users\\me\\Jarvis"}.')
    if not shutil.which("claude"):
        return INSTALL
    project, folder = _folder(a.get("project"))
    if not folder:
        return f"Which project? Known ones: {', '.join(PROJECTS)}."
    if not os.path.isdir(folder):
        return f"The folder for {project} doesn't exist: {folder}"
    task = (a.get("task") or "").strip()
    if not task:
        return "No task given."
    _draft = (project, folder, task, bool(a.get("continue_last")), skills.turn, time.monotonic(), False)
    return (f"Ready to ask Claude Code, in {project}: \"{task}\". Read the task back to him in a few "
            "words and ask whether to start. Only call start_claude_code_task after he says yes.")


def plan_app(a):
    """A new small app or web page, built by Claude Code in its own folder."""
    global _draft
    if not shutil.which("claude"):
        return INSTALL
    what = (a.get("what") or "").strip()
    if not what:
        return "Say what the app should do."
    from skills import files
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", a.get("name") or what)
    name = re.sub(r"\s+", " ", name).strip()[:40] or "app"
    taken = next((k for k in PROJECTS if k.lower() == name.lower()), None)
    if taken:
        return (f"There's already an app called {taken}. To change it use plan_claude_code_task with "
                f"project \"{taken}\", or pick another name.")
    folder = files._unique(os.path.join(files._folder("documents") or os.path.expanduser("~"), APPS_FOLDER, name))
    task = APP_TASK.format(what=what + (f". {a['details']}" if a.get("details") else ""))
    _draft = (name, folder, task, False, skills.turn, time.monotonic(), True)
    return (f"Ready to have Claude Code build \"{name}\" ({what}) in Documents/{APPS_FOLDER}. It takes a few "
            "minutes and uses his Claude plan. Read that back in a few words and ask whether to start. Only call "
            "start_claude_code_task after he says yes.")


def start_task(a):
    global _draft
    if _draft is None:
        return "There's no task waiting. Use plan_claude_code_task first."
    project, folder, task, cont, made_in, made_at, new_app = _draft
    if skills.turn <= made_in:
        return "Wait for him to say yes first: read the task back and ask."
    if time.monotonic() - made_at > DRAFT_MINUTES * 60:
        _draft = None
        return "That task was planned too long ago; plan it again."
    if project in _running:
        return f"Claude Code is already working on {project}."
    _draft = None
    if new_app:
        os.makedirs(folder, exist_ok=True)
    _running[project] = time.monotonic()
    threading.Thread(target=_run, args=(project, folder, task, cont, new_app), daemon=True).start()
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
        "name": "plan_new_app",
        "description": (
            "Have Claude Code build a NEW small app, tool, game or web page for him ('build me a pomodoro "
            "timer', 'make a web page for my study schedule', 'a little app to track my marks'). Step 1 of 2: "
            "this only prepares it; start_claude_code_task starts it after he says yes. To change an app "
            "built before, use plan_claude_code_task with its name as project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "what it should do, in his words"},
                "details": {"type": "string", "description": "looks, features, Python vs web page"},
                "name": {"type": "string", "description": "short name, e.g. 'pomodoro'"},
            },
            "required": ["what"],
        },
        "run": plan_app,
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
