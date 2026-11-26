"""Sticky notes for when he's back: "remind me to email the prof when I get
back to my PC". Jarvis says them the moment he's back: the keyboard or mouse
is used again after being away (Windows), or the next time Jarvis starts.
Saved in memory/sticky.json, so a restart doesn't lose them.
"""
import sys
import threading
import time

import config
from brain import memory

FILE = "sticky.json"
AWAY_MINUTES = getattr(config, "AWAY_MINUTES", 5)   # this long with no keyboard or mouse = away
CHECK_EVERY = 5

_started = False


def _load():
    notes = memory._read(FILE, [])
    return notes if isinstance(notes, list) else []


def idle_seconds() -> float:
    """Seconds since the keyboard or mouse was last used (Windows); 0 elsewhere."""
    if sys.platform != "win32":
        return 0.0
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0
    except Exception:
        return 0.0


def deliver(reason="back") -> bool:
    """Say the notes (and clear them). Returns True if there were any."""
    notes = _load()
    if not notes:
        return False
    memory._write(FILE, [])
    items = [n["text"] for n in notes]
    if len(items) == 1:
        line = f"Welcome back, sir. You asked me to remind you: {items[0]}."
    else:
        line = "Welcome back, sir. You asked me to remind you of a few things: " + "; ".join(items) + "."
    from skills import timers
    timers.announce(line)
    print(f"[sticky] delivered {len(items)} note(s) ({reason})")
    return True


def _watch():
    away = False
    while True:
        idle = idle_seconds()
        if idle >= AWAY_MINUTES * 60:
            away = True
        elif away and idle < CHECK_EVERY * 2:
            away = False
            try:
                deliver("back at the PC")
            except Exception as e:
                print(f"[sticky] couldn't say the notes: {e}")
        time.sleep(CHECK_EVERY)


def start():
    """At startup: he's at the PC now, so say any notes left; then watch for him coming back."""
    global _started
    try:
        deliver("Jarvis started")
    except Exception as e:
        print(f"[sticky] {e}")
    if sys.platform == "win32" and not _started:
        _started = True
        threading.Thread(target=_watch, daemon=True, name="sticky").start()


def remind_when_back(a):
    action = str(a.get("action") or "add").lower()
    notes = _load()
    if action == "list":
        if not notes:
            return "No notes waiting for when he's back."
        return "Waiting for when he's back: " + "; ".join(n["text"] for n in notes) + "."
    if action == "clear":
        memory._write(FILE, [])
        return f"Cleared {len(notes)} note{'s' * (len(notes) != 1)}."
    text = str(a.get("text") or "").strip().rstrip(".")
    if not text:
        return "What should I remind him of when he's back?"
    notes.append({"text": text[:200], "at": time.time()})
    memory._write(FILE, notes[-20:])
    when = (f"when he's back at the PC (after {AWAY_MINUTES} minutes away)" if sys.platform == "win32"
            else "the next time Jarvis starts")
    return f"Noted. I'll remind him {when}: {text}."


SKILLS = [
    {
        "name": "remind_when_back",
        "description": "A reminder for when he's back at his PC, not at a set time ('remind me to email the prof "
                       "when I get back'). action add (default), list or clear.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "action": {"type": "string", "enum": ["add", "list", "clear"]}}},
        "run": remind_when_back,
    },
]
