"""Long jobs run in the background, so he can talk to Jarvis meanwhile.

Screen control, carrying out a file sort, 3D parts, documents, whiteboard
drawings and "what's the buzz" research can take a while. Asked for in a live
conversation, they start here and Jarvis says he's on it; he can be asked
anything else in the meantime. When a job finishes, he tells you at the next
quiet moment (not in the middle of another conversation).

Screen-control jobs use the mouse and keyboard, so only one runs at a time:
the next one waits its turn. The others run side by side.

"What are you working on?" lists them; "cancel that" stops one.
"""
import itertools
import threading
import time

import config
import ui_events

# Tools that run in the background when started from a live conversation.
LONG = {"use_computer", "make_3d_model", "make_document", "whats_the_buzz", "organize_folder",
        "canvas_download"}
SCREEN = {"use_computer"}     # need the mouse and keyboard: one at a time
KEEP_FINISHED = 300           # seconds a finished job is still listed

_lock = threading.Lock()
_screen = threading.Lock()
_ids = itertools.count(1)
_tasks = {}


class Task:
    def __init__(self, name, args, label):
        self.id = next(_ids)
        self.name, self.args, self.label = name, dict(args or {}), label
        self.state = "queued"         # queued, running, done, failed, cancelled
        self.result = ""
        self.started = time.time()
        self.finished = None
        self.cancel = threading.Event()

    def describe(self):
        mins = (time.time() - self.started) / 60
        age = "just now" if mins < 1 else f"{mins:.0f} min"
        return {"queued": f"{self.label} (waiting for the screen)",
                "running": f"{self.label} (running, {age})",
                "done": f"{self.label} (finished)", "failed": f"{self.label} (failed)",
                "cancelled": f"{self.label} (cancelled)"}[self.state]


def enabled() -> bool:
    return bool(getattr(config, "BACKGROUND_TASKS", True))


def wants(name: str, args: dict, live: bool) -> bool:
    """Run this tool call in the background? Only from a live conversation
    (scheduled jobs and the phone bot want the answer straight back), and a
    sort only once he's said yes (making the plan is quick)."""
    if not (enabled() and live and name in LONG) or threading.current_thread().name.startswith("task-"):
        return False
    if name == "organize_folder":
        return bool(args.get("confirmed")) and not args.get("cancel")
    if name == "use_computer":
        from skills import computer
        task = str(args.get("task") or "")
        return not (computer._DRAWING.search(task) or computer._FILE_JOB.search(task))
    return True


def start(name: str, args: dict, run, label: str = "") -> str:
    """Start run(args) in its own thread; returns what Jarvis should say now."""
    from brain import paid
    label = (label or name.replace("_", " ")).rstrip(".").rstrip()
    task = Task(name, args, label)
    with _lock:
        _prune()
        busy_screen = name in SCREEN and any(t.name in SCREEN and t.state in ("queued", "running")
                                             for t in _tasks.values())
        _tasks[task.id] = task
    paid_ok = paid.carry()   # a yes to Claude covers the whole job

    def work():
        paid.set_for_thread(paid_ok)
        screen = name in SCREEN
        if screen:
            _screen.acquire()
        try:
            if task.cancel.is_set():
                return
            task.state = "running"
            ui_events.task(label + "...")
            ok = True
            try:
                task.result = str(run(args))
            except Exception as e:
                ok = False
                task.result = f"The {name} tool failed: {e}"
            if task.cancel.is_set():
                return
            task.state = "done" if ok else "failed"
            task.finished = time.time()
            ui_events.task_done(ok)
            print(f"[task {task.id}] {label} {task.state}: {task.result[:150]}")
            _announce(task)
        finally:
            if screen:
                _screen.release()

    threading.Thread(target=work, daemon=True, name=f"task-{task.id}").start()
    print(f"[task {task.id}] started in the background: {label} {args}")
    wait = " It's queued behind the screen job already running." if busy_screen else ""
    return (f"Started in the background: {label}.{wait} Tell him in one short sentence that you're on it and "
            "he can ask you other things meanwhile; you'll tell him when it's done. Don't say it's done yet.")


def _announce(task):
    """Tell him at the next quiet moment: the main loop picks this up while
    waiting for "Hey Jarvis" (or the next typed message)."""
    note = (f"[A background job you started earlier has finished: {task.label}. Its result: {task.result}]\n"
            "Tell him the outcome now in one or two short sentences, starting with something like "
            f"\"Sir, about {task.label[0].lower() + task.label[1:]}:\". If it needs his answer, ask.")
    if config.MODE == "wake" or ui_events.gui_active:
        ui_events.inbox.put(("task_result", note))
    else:
        from skills import timers
        timers.announce(f"Sir, {task.label} has finished.")


def _prune():
    now = time.time()
    for k in [k for k, t in _tasks.items() if t.finished and now - t.finished > KEEP_FINISHED]:
        _tasks.pop(k, None)


def active():
    with _lock:
        _prune()
        return [t for t in _tasks.values() if t.state in ("queued", "running")]


# ---------- tools ----------

def list_tasks(a=None):
    with _lock:
        _prune()
        tasks = sorted(_tasks.values(), key=lambda t: t.id)
    if not tasks:
        return "Nothing is running in the background."
    return "Background jobs: " + "; ".join(f"{t.id}. {t.describe()}" for t in tasks) + "."


def cancel_task(a):
    """Stop one job: the one named, else the newest still going."""
    want = str((a or {}).get("which") or "").strip().lower()
    live = active()
    if not live:
        return "Nothing is running in the background to cancel."
    pick = None
    if want.isdigit():
        pick = next((t for t in live if t.id == int(want)), None)
    elif want and want not in ("it", "that", "this", "the task", "last", "latest", "newest"):
        pick = next((t for t in reversed(live) if want in t.label.lower() or want in t.name), None)
    if want in ("all", "everything"):
        for t in live:
            _stop(t)
        return f"Cancelled {len(live)} background job{'s' if len(live) > 1 else ''}."
    pick = pick or live[-1]
    _stop(pick)
    return f"Cancelled: {pick.label}."


def _stop(task):
    was_running = task.state == "running"
    task.cancel.set()
    task.state, task.finished = "cancelled", time.time()
    if task.name in SCREEN and was_running:
        ui_events.cancel.set()   # screen control checks this between steps
    ui_events.task_done(False)
    print(f"[task {task.id}] cancelled: {task.label}")


SKILLS = [
    {
        "name": "list_tasks",
        "description": "What Jarvis is working on in the background right now ('what are you working on?', "
                       "'is that done yet?').",
        "parameters": {"type": "object", "properties": {}},
        "run": list_tasks,
    },
    {
        "name": "cancel_task",
        "description": "Stop a background job ('cancel that', 'stop the screen task', 'cancel everything').",
        "parameters": {"type": "object", "properties": {
            "which": {"type": "string", "description": "its number, a word from it, 'all', or empty for the newest"}}},
        "run": cancel_task,
    },
]
