"""Control the computer by voice: open apps, volume, media keys, lock screen.

Windows uses the system's virtual media/volume keys (no extra packages).
On Linux (e.g. the Raspberry Pi) it uses amixer and playerctl when they're installed.
Apps are only opened from the APPS list in config.py or the Start menu's shortcuts,
so Jarvis can't be talked into running arbitrary commands.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import time

import config

IS_WINDOWS = sys.platform == "win32"

# Windows virtual-key codes
VK = {"volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
      "next": 0xB0, "previous": 0xB1, "stop": 0xB2, "play_pause": 0xB3}
VOLUME_STEP = 2  # each Windows volume key press moves the volume by 2%


def _press(key, times=1):
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(VK[key], 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK[key], 0, 2, 0)  # key up
        if times > 1:
            time.sleep(0.01)


def _run(cmd):
    if not shutil.which(cmd[0]):
        return False
    return subprocess.run(cmd, capture_output=True, timeout=5).returncode == 0


# ---------- apps ----------
def _start_menu_shortcuts():
    roots = [os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
             os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
    found = {}
    for root in roots:
        for path in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            found.setdefault(os.path.splitext(os.path.basename(path))[0].lower(), path)
    return found


def _norm(name):
    return " ".join(name.lower().replace("-", " ").split())


def open_app(a):
    name = _norm(a.get("name", ""))
    if not name:
        return "No app name given."
    if re.fullmatch(r"(?:the |your |my )?(?:jarvis'?s? |microsoft |ms )?(?:white ?board|drawing board|board)(?: app)?", name):
        from skills import whiteboard
        return whiteboard.whiteboard_step({"action": "open"})
    apps = {_norm(k): v for k, v in config.APPS.items()}
    target = apps.get(name)
    if target is None and IS_WINDOWS:
        shortcuts = _start_menu_shortcuts()
        target = shortcuts.get(name)
        if target is None:  # "spotify" matches "Spotify", "word" matches "Microsoft Word"...
            hits = sorted((k for k in shortcuts if name in k and "uninstall" not in k), key=len)
            target = shortcuts[hits[0]] if hits else None
    if target is None:
        site = re.sub(r"\s+(?:for me|please|now)$", "", name)
        from skills.quick_actions import SITES, open_website
        if site in SITES:  # "youtube" is a website, not an installed app
            return open_website({"site": site})
        return f"I don't know an app called {name}. Add it to APPS in config.py."
    try:
        if IS_WINDOWS:
            os.startfile(target)
        else:
            subprocess.Popen(target if isinstance(target, list) else [target],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return f"Couldn't open {name}: {e}"
    return f"Opened {name}."


# ---------- volume ----------
def set_volume(a):
    action = (a.get("action") or "").lower()
    level = a.get("level")
    if IS_WINDOWS:
        if action == "mute":
            _press("volume_mute")
            return "Toggled mute."
        if action in ("up", "down"):
            steps = max(1, int(a.get("amount", 10)) // VOLUME_STEP)
            _press("volume_" + action, steps)
            return f"Volume {action} {steps * VOLUME_STEP}%."
        if action == "set" and level is not None:
            level = max(0, min(100, int(level)))
            _press("volume_down", 50)  # to zero, then up to the level
            _press("volume_up", round(level / VOLUME_STEP))
            return f"Volume set to {level}%."
        return "Say up, down, mute, or set with a level."
    # Linux / Pi
    if action == "mute":
        ok = _run(["amixer", "-q", "sset", "Master", "toggle"])
    elif action in ("up", "down"):
        ok = _run(["amixer", "-q", "sset", "Master", f"{int(a.get('amount', 10))}%{'+' if action == 'up' else '-'}"])
    elif action == "set" and level is not None:
        ok = _run(["amixer", "-q", "sset", "Master", f"{max(0, min(100, int(level)))}%"])
    else:
        return "Say up, down, mute, or set with a level."
    return "Done." if ok else "Volume control isn't available here (needs amixer)."


# ---------- media ----------
def media(a):
    action = (a.get("action") or "").lower().replace(" ", "_")
    if action in ("play", "pause", "resume"):
        action = "play_pause"
    if action not in ("play_pause", "next", "previous", "stop"):
        return "Say play, pause, next, previous or stop."
    if IS_WINDOWS:
        _press(action)
        return "Done."
    cmd = {"play_pause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}[action]
    return "Done." if _run(["playerctl", cmd]) else "Media control isn't available here (needs playerctl)."


def lock_screen(a=None):
    if IS_WINDOWS:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "Locked."
    return "Done." if _run(["loginctl", "lock-session"]) else "Can't lock the screen here."


SKILLS = [
    {
        "name": "open_app",
        "description": "Open an installed app on the user's computer by name, e.g. Chrome, Spotify, Apple Music, Notepad, Calculator, VS Code. Websites (YouTube, Gmail, Netflix...) use open_website instead.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        "run": open_app,
    },
    {
        "name": "set_volume",
        "description": "Change the computer's speaker volume.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["up", "down", "set", "mute"],
                           "description": "mute toggles mute"},
                "amount": {"type": "integer", "description": "Percent for up/down (default 10)"},
                "level": {"type": "integer", "description": "0-100, for set"},
            },
            "required": ["action"],
        },
        "run": set_volume,
    },
    {
        "name": "media",
        "description": "Control whatever music or video is playing (Spotify, YouTube, etc.).",
        "parameters": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["play_pause", "next", "previous", "stop"]}},
            "required": ["action"],
        },
        "run": media,
    },
    {
        "name": "lock_screen",
        "description": "Lock the computer.",
        "parameters": {"type": "object", "properties": {}},
        "run": lock_screen,
    },
]
