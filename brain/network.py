"""Is the internet up? Answers in well under a second and remembers the answer
for a few seconds, so Jarvis never sits through a 10 second timeout to find
out the wifi is down. With no internet he still does the basics
(brain/offline.py)."""
import socket
import threading
import time

import config

# Public DNS servers: tiny TCP connects that need no DNS lookup themselves.
HOSTS = [("1.1.1.1", 53), ("8.8.8.8", 53), ("1.1.1.1", 443)]
TIMEOUT = 0.8          # seconds per host
REMEMBER_ONLINE = 30   # seconds a good check is trusted
REMEMBER_OFFLINE = 8   # seconds before checking again once it's down

_lock = threading.Lock()
_state = {"online": None, "until": 0.0}


def _check() -> bool:
    for host in HOSTS:
        try:
            socket.create_connection(host, timeout=TIMEOUT).close()
            return True
        except OSError:
            continue
    return False


def _set(up: bool):
    was = _state["online"]
    _state["online"] = up
    _state["until"] = time.monotonic() + (REMEMBER_ONLINE if up else REMEMBER_OFFLINE)
    if was is not None and was != up:
        print("[network] back online" if up else "[network] offline: doing the basics locally")


def online() -> bool:
    if getattr(config, "OFFLINE_MODE", False):
        return False
    with _lock:
        if time.monotonic() >= _state["until"]:
            _set(_check())
        return _state["online"]


def mark_offline():
    """A request just failed to connect: treat the internet as down for a bit."""
    with _lock:
        _set(False)


_NAMES = {"ConnectionError", "ConnectTimeout", "APIConnectionError", "APITimeoutError",
          "NewConnectionError", "NameResolutionError", "gaierror", "MaxRetryError"}
_TEXT = ("name resolution", "getaddrinfo failed", "failed to establish a new connection",
         "network is unreachable", "no route to host", "nodename nor servname",
         "temporary failure in name resolution", "connection aborted")


def is_network_error(e: BaseException) -> bool:
    """True when e means "couldn't reach the server" (no internet), as
    opposed to the server answering with an error."""
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if any(c.__name__ in _NAMES for c in type(e).__mro__):
            return True
        if any(t in str(e).lower() for t in _TEXT):
            return True
        e = e.__cause__ or e.__context__
    return False
