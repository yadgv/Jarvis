"""Turning Jarvis off by voice."""

shutdown_requested = False


def shut_down(a=None):
    global shutdown_requested
    shutdown_requested = True
    return "Jarvis will power down after this reply. Say a brief goodbye."


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
]
