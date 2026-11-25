"""Turning Jarvis off by voice, and starting him with Windows."""

shutdown_requested = False


def shut_down(a=None):
    global shutdown_requested
    shutdown_requested = True
    return "Jarvis will power down after this reply. Say a brief goodbye."


def start_with_windows(a):
    import autostart
    return autostart.set_on(bool(a.get("on", True)))


SKILLS = [
    {
        "name": "shut_down",
        "description": (
            "Turn Jarvis off. Use only when the user clearly wants you to stop running: "
            "'shut down', 'power off', 'turn yourself off', 'goodbye', 'that's all, go to sleep'. "
            "Not for shutting down other devices."
        ),
        "parameters": {"type": "object", "properties": {}},
        "run": shut_down,
    },
    {
        "name": "start_with_windows",
        "description": "Turn on or off starting Jarvis automatically when the user logs in to Windows.",
        "parameters": {"type": "object", "properties": {
            "on": {"type": "boolean", "description": "true to start at login, false to stop"}},
            "required": ["on"]},
        "run": start_with_windows,
    },
]
