"""Startup timing: how long each part takes before Jarvis is ready, in the log.

    [startup] speech recognition loaded in 2.1s (4.3s since launch)
"""
import time

T0 = time.perf_counter()


def mark(what: str, since: float = None) -> float:
    now = time.perf_counter()
    took = f" in {now - since:.1f}s" if since is not None else ""
    print(f"[startup] {what}{took} ({now - T0:.1f}s since launch)")
    return now
