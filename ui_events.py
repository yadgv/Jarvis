"""A tiny bridge between the voice loop and any window (gui.py).

The voice loop calls emit() when something happens; a window subscribes with
on(). The window sends things back through `inbox` (typed messages, the Talk
button) and `stop_speaking` (the Stop button). With no window open, nothing
listens and everything works exactly as before.
"""
import queue
import threading

_listeners = []
inbox = queue.Queue()            # ("text", "what's the weather") or ("talk", None)
stop_speaking = threading.Event()
gui_active = False


def on(fn):
    _listeners.append(fn)


def emit(kind, text=""):
    """kind: status (idle/listening/thinking/speaking), you, jarvis, info."""
    for fn in list(_listeners):
        try:
            fn(kind, text)
        except Exception:
            pass


def poll():
    """Next request from the window, or None."""
    try:
        return inbox.get_nowait()
    except queue.Empty:
        return None
