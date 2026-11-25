"""Timers and alarms. When one goes off, Jarvis says so out loud.

main.py sets `announce` to a function that speaks a message; until then
finished timers are just printed.
"""
import itertools
import threading
import time
from datetime import datetime, timedelta

announce = print  # replaced by main.py with a function that speaks

_lock = threading.Lock()
_timers = {}  # id -> {"label", "due", "timer"}
_ids = itertools.count(1)


def _fire(tid):
    with _lock:
        t = _timers.pop(tid, None)
    if t:
        announce(f"Sir, your {t['label']} is done." if t["kind"] == "timer"
                 else f"Sir, it's time: {t['label']}.")


def _start(label, delay, kind):
    tid = next(_ids)
    timer = threading.Timer(delay, _fire, args=(tid,))
    timer.daemon = True
    with _lock:
        _timers[tid] = {"label": label, "due": time.time() + delay, "timer": timer, "kind": kind}
    timer.start()
    return tid


def _say_duration(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h: parts.append(f"{h} hour{'s' * (h != 1)}")
    if m: parts.append(f"{m} minute{'s' * (m != 1)}")
    if s or not parts: parts.append(f"{s} second{'s' * (s != 1)}")
    return " ".join(parts)


def set_timer(a):
    seconds = float(a.get("seconds", 0))
    if seconds <= 0:
        return "The duration must be more than zero seconds."
    label = (a.get("label") or "timer").strip()
    if "timer" not in label.lower():
        label += " timer"
    _start(label, seconds, "timer")
    return f"Timer set: {label}, {_say_duration(seconds)}."


def set_alarm(a):
    try:
        hh, mm = (int(x) for x in str(a.get("time", "")).split(":")[:2])
        target = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    except ValueError:
        return "Give the time as HH:MM in 24-hour format."
    if target <= datetime.now():
        target += timedelta(days=1)
    label = (a.get("label") or "alarm").strip()
    _start(label, (target - datetime.now()).total_seconds(), "alarm")
    return f"Alarm set for {target.strftime('%H:%M')} ({target.strftime('%A')}): {label}."


def list_timers(a=None):
    with _lock:
        items = sorted(_timers.values(), key=lambda t: t["due"])
    if not items:
        return "No timers or alarms are running."
    now = time.time()
    return "; ".join(f"{t['label']}: {_say_duration(t['due'] - now)} left" for t in items)


def cancel_timer(a):
    label = (a.get("label") or "").strip().lower()
    with _lock:
        if label in ("", "all", "everything"):
            hits = list(_timers)
        else:
            hits = [k for k, t in _timers.items() if label in t["label"].lower()]
        for k in hits:
            _timers.pop(k)["timer"].cancel()
    return f"Cancelled {len(hits)}." if hits else "No matching timer or alarm."


SKILLS = [
    {
        "name": "set_timer",
        "description": "Start a countdown timer. Convert the user's duration to seconds.",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "description": "Duration in seconds"},
                "label": {"type": "string", "description": "Short name, e.g. 'tea' or 'pasta'"},
            },
            "required": ["seconds"],
        },
        "run": set_timer,
    },
    {
        "name": "set_alarm",
        "description": "Set an alarm or reminder for a clock time today (or tomorrow if that time has passed).",
        "parameters": {
            "type": "object",
            "properties": {
                "time": {"type": "string", "description": "24-hour local time, HH:MM"},
                "label": {"type": "string", "description": "What it's for, e.g. 'call mum'"},
            },
            "required": ["time"],
        },
        "run": set_alarm,
    },
    {
        "name": "list_timers",
        "description": "List running timers and alarms with the time left.",
        "parameters": {"type": "object", "properties": {}},
        "run": list_timers,
    },
    {
        "name": "cancel_timer",
        "description": "Cancel timers or alarms whose name contains the given words, or 'all'.",
        "parameters": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
        "run": cancel_timer,
    },
]
