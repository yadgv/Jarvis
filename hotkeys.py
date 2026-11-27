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
# Windows virtual-key codes for the modifiers, to check they're really down.
VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": (0x5B, 0x5C)}


def _down(vk) -> bool:
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def really_held(combo: str) -> bool:
    """pynput can miss a key-up (focus jumps to the orb mid-shortcut, or keys
    injected by another app), then thinks Ctrl+Alt are still down: every "h"
    or "j" typed anywhere fired a shortcut, hiding the text panel and closing
    the text box while he typed in it. Ask Windows whether the modifiers are
    actually down right now. Other systems: trust pynput."""
    import sys
    if sys.platform != "win32":
        return True
    try:
        for m in combo.split("+")[:-1]:
            codes = VK[m] if isinstance(VK[m], tuple) else (VK[m],)
            if not any(_down(c) for c in codes):
                return False
    except Exception:
        return True
    return True


def _fire(combo, action, on_action):
    if not really_held(combo):
        print(f"[hotkeys] ignored {combo.upper()}: the keys weren't really held (a stuck key)")
        return
    on_action(action)


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
        _listener = keyboard.GlobalHotKeys({to_pynput(c): (lambda c=c, a=a: _fire(c, a, on_action))
                                            for c, a in combos.items()})
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
