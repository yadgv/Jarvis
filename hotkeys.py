"""Keyboard shortcuts that work from any app (Settings > Look to change them).

  ctrl+alt+j   type to Jarvis: opens the text box with the cursor in it
  ctrl+alt+h   show or hide the whole text panel next to the orb

Written like "ctrl+alt+j", "ctrl+shift+space" or "f8". Uses pynput (already
needed for F9 dictation); does nothing if it isn't installed.
"""
import re

DEFAULTS = {"type_key": "ctrl+alt+j", "panel_key": "ctrl+alt+h"}
MODIFIERS = {"ctrl": "<ctrl>", "control": "<ctrl>", "alt": "<alt>", "shift": "<shift>",
             "win": "<cmd>", "windows": "<cmd>", "cmd": "<cmd>"}
NAMED = {"space", "tab", "enter", "esc", "home", "end", "insert", "delete", "page_up", "page_down",
         "up", "down", "left", "right", "backspace"}

_listener = None


def normal(combo: str) -> str:
    """ "Ctrl + Alt + J" -> "ctrl+alt+j"; "" if it isn't a usable shortcut."""
    parts = [p for p in re.sub(r"\s+", "", (combo or "").lower()).split("+") if p]
    if not parts:
        return ""
    *mods, key = parts
    mods = ["ctrl" if m == "control" else "win" if m in ("windows", "cmd") else m for m in mods]
    if any(m not in MODIFIERS for m in mods) or len(set(mods)) != len(mods):
        return ""
    fkey = re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key)
    if not (len(key) == 1 and key.isalnum() or fkey or key in NAMED):
        return ""
    if not mods and not fkey:
        return ""    # a plain letter would fire every time he types it
    order = [m for m in ("ctrl", "alt", "shift", "win") if m in mods]
    return "+".join(order + [key])


def to_pynput(combo: str) -> str:
    """ "ctrl+alt+j" -> "<ctrl>+<alt>+j" (pynput's format)."""
    *mods, key = combo.split("+")
    key = f"<{key}>" if len(key) > 1 else key
    return "+".join([MODIFIERS[m] for m in mods] + [key])


def pick(prefs: dict, dictation_key: str = "") -> dict:
    """{combo: action} from the saved settings, skipping clashes (with each other and F9 dictation)."""
    out = {}
    for action, default in DEFAULTS.items():
        combo = normal(prefs.get(action) or "") or default
        if combo in out or combo == normal(dictation_key or ""):
            print(f"[hotkeys] {combo} is already used, so {action} is off")
            continue
        out[combo] = action
    return out


def start(prefs: dict, on_action, dictation_key: str = "") -> dict:
    """Listen for the shortcuts; on_action(action) runs on pynput's thread. Restarts if already on."""
    global _listener
    stop()
    combos = pick(prefs, dictation_key)
    try:
        from pynput import keyboard
    except ImportError:
        print("[hotkeys] keyboard shortcuts need: pip install pynput")
        return {}
    try:
        _listener = keyboard.GlobalHotKeys({to_pynput(c): (lambda a=a: on_action(a)) for c, a in combos.items()})
        _listener.daemon = True
        _listener.start()
    except Exception as e:
        print(f"[hotkeys] couldn't start the shortcuts: {e}")
        _listener = None
        return {}
    names = {"type_key": "type to Jarvis", "panel_key": "show/hide the text"}
    print("[hotkeys] " + ", ".join(f"{c.upper()} = {names[a]}" for c, a in combos.items()))
    return combos


def stop():
    global _listener
    if _listener is not None:
        try:
            _listener.stop()
        except Exception:
            pass
        _listener = None
