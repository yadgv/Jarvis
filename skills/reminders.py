"""Reminders for any day and time. Unlike timers they're saved to
memory/reminders.json, so they survive a restart; any that came due while
Jarvis was off are read out when he starts.
"""
import threading
import time
import uuid
from datetime import datetime, timedelta

from brain import memory
from skills import timers

FILE = "reminders.json"
CHECK_EVERY = 15  # seconds
_lock = threading.Lock()
_started = False


def _load():
    return memory._read(FILE, [])


def _save(items):
    memory._write(FILE, items)


def _say(dt):
    hour = dt.strftime("%I").lstrip("0") or "12"
    clock = f"{hour}:{dt.strftime('%M %p')}" if dt.minute else f"{hour} {dt.strftime('%p')}"
    today = datetime.now().date()
    if dt.date() == today:
        day = "today"
    elif dt.date() == today + timedelta(days=1):
        day = "tomorrow"
    else:
        day = dt.strftime("%A %d %B")
    return f"{day} at {clock}"


def set_reminder(a):
    text = (a.get("text") or "").strip()
    if not text:
        return "What should I remind him about?"
    if a.get("in_minutes"):
        due = datetime.now() + timedelta(minutes=float(a["in_minutes"]))
    else:
        try:
            due = datetime.fromisoformat((a.get("when") or "").strip())
        except ValueError:
            return "Give when as YYYY-MM-DDTHH:MM local time, or in_minutes."
        if due.tzinfo:
            due = due.astimezone().replace(tzinfo=None)
    if due <= datetime.now():
        return "That time has already passed."
    with _lock:
        items = _load()
        items.append({"id": uuid.uuid4().hex[:8], "text": text, "due": due.isoformat(timespec="minutes")})
        _save(items)
    return f"Reminder set for {_say(due)}: {text}."


def list_reminders(a=None):
    items = sorted(_load(), key=lambda r: r["due"])
    if not items:
        return "No reminders set."
    return "\n".join(f"- {_say(datetime.fromisoformat(r['due']))}: {r['text']}" for r in items)


def cancel_reminder(a):
    words = (a.get("text") or "").strip().lower()
    with _lock:
        items = _load()
        if words in ("", "all", "everything"):
            keep = []
        else:
            keep = [r for r in items if words not in r["text"].lower()]
        _save(keep)
    gone = len(items) - len(keep)
    return f"Cancelled {gone} reminder{'s' * (gone != 1)}." if gone else "No matching reminder."


def check(now=None):
    """Say any reminders that are due and remove them. Returns how many."""
    now = now or datetime.now()
    with _lock:
        items = _load()
        due = [r for r in items if datetime.fromisoformat(r["due"]) <= now]
        if due:
            _save([r for r in items if r not in due])
    for r in sorted(due, key=lambda r: r["due"]):
        late = now - datetime.fromisoformat(r["due"])
        if late > timedelta(minutes=5):
            timers.announce(f"Sir, a reminder I missed while I was off, from {_say(datetime.fromisoformat(r['due']))}: {r['text']}.")
        else:
            timers.announce(f"Sir, a reminder: {r['text']}.")
    return len(due)


def start():
    """Begin checking for due reminders in the background (main.py calls this)."""
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                check()
            except Exception as e:
                print(f"[reminders] check failed: {e}")
            time.sleep(CHECK_EVERY)
    threading.Thread(target=loop, daemon=True).start()


SKILLS = [
    {
        "name": "set_reminder",
        "description": (
            "Remind the user about something at a given time, any day ('remind me to call mum on Friday at 6', "
            "'remind me in 20 minutes to check the oven'). Saved, so it works even after a restart. "
            "Work out the exact local date and time from the current date in your instructions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to remind him about, e.g. 'call mum'"},
                "when": {"type": "string", "description": "Local time YYYY-MM-DDTHH:MM"},
                "in_minutes": {"type": "number", "description": "Instead of when: minutes from now"},
            },
            "required": ["text"],
        },
        "run": set_reminder,
    },
    {
        "name": "list_reminders",
        "description": "List the user's upcoming reminders.",
        "parameters": {"type": "object", "properties": {}},
        "run": list_reminders,
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel reminders whose text contains the given words, or 'all'.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        "run": cancel_reminder,
    },
]
