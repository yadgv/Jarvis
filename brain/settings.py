"""Settings he can change by voice ("talk faster", "be more casual", "call me Ziad")
or in the orb's right-click Settings window. Saved in memory/settings.json;
config.py holds the defaults."""
import config
from brain import memory

FILE = "settings.json"

# How each style sounds; added to the system prompt.
STYLES = {
    "butler": "Speak like a witty, dry British butler: polite, understated, the odd bit of humour.",
    "casual": "Speak casually and warmly, like a friend: relaxed wording, contractions, light humour.",
    "brief": "Be as brief as possible: answer in one short sentence, no small talk, no humour.",
    "formal": "Speak formally and precisely, like a professional assistant. No jokes.",
    "playful": "Be playful and cheeky, with plenty of humour, but still get to the point.",
}
LENGTHS = {
    "short": "Keep replies to 1-2 short sentences.",
    "normal": "Keep replies short: 1-3 sentences.",
    "long": "You may give fuller answers, up to 5 or 6 sentences, when the question deserves it.",
}
MIN_SPEED, MAX_SPEED = 0.7, 1.5


def defaults():
    return {
        "style": getattr(config, "STYLE", "butler"),
        "length": getattr(config, "REPLY_LENGTH", "normal"),
        "call_me": getattr(config, "CALL_ME", "sir"),
        "speed": float(getattr(config, "VOICE_SPEED", 1.0)),
        "voice": getattr(config, "VOICE", "jarvis"),
        "offline_voice": getattr(config, "OFFLINE_VOICE", "fable"),
    }


def load() -> dict:
    s = defaults()
    saved = memory._read(FILE, {})
    if isinstance(saved, dict):
        s.update({k: v for k, v in saved.items() if k in s})
    return s


# ---------- the Settings window (right-click the orb) ----------
# Config values as config.py set them, so "on" can be put back after "off".
_ATTRS = ("WAKE_THRESHOLD", "WAKE_CHIME", "FOLLOWUP_SECONDS", "OFFLINE_MODE", "LOCAL_MODEL", "DUCK_APPS",
          "ROOM_CONTEXT", "TELEGRAM_ON", "MORNING_BRIEFING", "TEMPERATURE_UNIT", "MIC_DEVICE")
_ORIGINAL = {a: getattr(config, a, None) for a in _ATTRS}
_ORIGINAL["DUCK_APPS"] = list(_ORIGINAL["DUCK_APPS"] or [])
_ORIGINAL["LOCAL_MODEL"] = _ORIGINAL["LOCAL_MODEL"] or ""


def _orig(attr, default=None):
    v = _ORIGINAL.get(attr)
    return default if v is None else v
ORB_SIZES = {"small": 96, "medium": 128, "large": 168}
CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")
COLOURS = {"orb_color": "#cdd7e1", "listening_color": "#78eba9", "thinking_color": "#f0b95a",
           "speaking_color": "#78c3ff", "text_color": "#f2f6fa"}


def _sensitivity(threshold) -> int:
    """Wake-word threshold (lower = wakes more easily) as 1-10 (higher = more sensitive)."""
    try:
        return max(1, min(10, round((0.75 - float(threshold)) / 0.05)))
    except (TypeError, ValueError):
        return 5


def threshold(sensitivity) -> float:
    return round(0.75 - 0.05 * max(1, min(10, int(sensitivity))), 2)


def app_defaults() -> dict:
    """The Settings window's own settings, with config.py's values as the defaults."""
    return {
        "show_panel": True,            # what you said and his reply, next to the orb
        "show_text_box": True,         # "Click here to type" under the reply
        **COLOURS,
        "orb_size": "medium",
        "corner": "top-right",
        "position": None,              # [right edge, top] after dragging; None = the corner
        "panel_seconds": 7,            # how long the text stays after he's done
        "whiteboard_on_top": True,
        "reduce_motion": False,        # fewer animations (slower PCs, or if they're distracting)
        "wake_sensitivity": _sensitivity(_orig("WAKE_THRESHOLD", 0.5)),
        "wake_chime": bool(_orig("WAKE_CHIME", True)),
        "followup_seconds": int(_orig("FOLLOWUP_SECONDS", 5)),
        "offline_mode": bool(_orig("OFFLINE_MODE", False)),
        "local_model": bool(_ORIGINAL["LOCAL_MODEL"]),
        "mic": "",                     # a microphone's name; "" = config.py's MIC_DEVICE
        "ducking": bool(_ORIGINAL["DUCK_APPS"]),
        "room_mode": bool(_orig("ROOM_CONTEXT", False)),
        "telegram": bool(_orig("TELEGRAM_ON", True)),
        "morning_briefing": bool(_orig("MORNING_BRIEFING", True)),
        "temperature_unit": str(_orig("TEMPERATURE_UNIT", "celsius")),
    }


def app() -> dict:
    s = app_defaults()
    saved = memory._read(FILE, {})
    if isinstance(saved, dict):
        s.update({k: v for k, v in saved.items() if k in s})
    return s


def _clean(key, value, default):
    """value in the same type as the default, or the default if it doesn't fit."""
    if key == "position":
        try:
            return [int(value[0]), int(value[1])] if value else None
        except (TypeError, ValueError, IndexError):
            return None
    if key in COLOURS:
        v = str(value or "").strip().lower()
        return v if len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdef" for c in v[1:]) else default
    if key == "orb_size":
        return value if value in ORB_SIZES else default
    if key == "corner":
        return value if value in CORNERS else default
    if key == "temperature_unit":
        return "fahrenheit" if str(value).lower().startswith("f") else "celsius"
    if isinstance(default, bool):
        return value.strip().lower() in ("1", "true", "on", "yes") if isinstance(value, str) else bool(value)
    if isinstance(default, int):
        try:
            v = int(float(value))
        except (TypeError, ValueError):
            return default
        limits = {"wake_sensitivity": (1, 10), "followup_seconds": (0, 30), "panel_seconds": (2, 60)}
        lo, hi = limits.get(key, (v, v))
        return max(lo, min(hi, v))
    return str(value or "").strip()[:120]


def save(values: dict) -> dict:
    """Save settings from the Settings window (voice settings too), then apply
    them. Returns what was saved."""
    voice_defaults, ui = defaults(), app_defaults()
    saved = memory._read(FILE, {})
    saved = saved if isinstance(saved, dict) else {}
    for key, value in (values or {}).items():
        if key in ui:
            saved[key] = _clean(key, value, ui[key])
        elif key in voice_defaults and change(key, value).startswith("Saved"):
            saved[key] = memory._read(FILE, {}).get(key, value)
    memory._write(FILE, saved)
    apply()
    return saved


def _mic_index(name):
    """The input device number for a microphone name (numbers change when
    devices are plugged in, names don't)."""
    if not name:
        return None
    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0 and d.get("name") == name:
                return i
    except Exception as e:
        print(f"[settings] couldn't list microphones: {e}")
    print(f"[settings] microphone '{name}' isn't plugged in; using the default one")
    return None


def microphones() -> list:
    """Names of the input devices, for the Settings window."""
    try:
        import sounddevice as sd
        names = [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception:
        return []
    return list(dict.fromkeys(names))


def apply():
    """Put the saved Settings-window choices into config, so the rest of
    Jarvis picks them up. Only what was saved is touched: config.py stays the
    default for everything else."""
    saved = memory._read(FILE, {})
    if not isinstance(saved, dict):
        return
    s = app()
    plain = {"wake_chime": "WAKE_CHIME", "followup_seconds": "FOLLOWUP_SECONDS", "offline_mode": "OFFLINE_MODE",
             "room_mode": "ROOM_CONTEXT", "telegram": "TELEGRAM_ON", "morning_briefing": "MORNING_BRIEFING",
             "temperature_unit": "TEMPERATURE_UNIT"}
    for key, attr in plain.items():
        if key in saved:
            setattr(config, attr, s[key])
    if "wake_sensitivity" in saved:
        config.WAKE_THRESHOLD = threshold(s["wake_sensitivity"])
    if "local_model" in saved:
        config.LOCAL_MODEL = (_ORIGINAL["LOCAL_MODEL"] or getattr(config, "OFFLINE_MODEL", "") or "llama3.2:3b") \
            if s["local_model"] else ""
    if "ducking" in saved:
        config.DUCK_APPS = (_ORIGINAL["DUCK_APPS"] or ["AppleMusic.exe", "iTunes.exe", "Spotify.exe"]) \
            if s["ducking"] else []
    if "mic" in saved:
        config.MIC_DEVICE = _mic_index(s["mic"]) if s["mic"] else _ORIGINAL["MIC_DEVICE"]


def reset_all():
    """Everything back to config.py's values (voice and personality too)."""
    memory._write(FILE, {})
    for attr, value in _ORIGINAL.items():
        if hasattr(config, attr) or value is not None:
            setattr(config, attr, list(value) if isinstance(value, list) else value)


def get(key):
    return load()[key]


def voice_id():
    """The Fish Audio voice to use."""
    voices = getattr(config, "VOICES", {}) or {}
    return voices.get(get("voice")) or config.FISH_VOICE_ID


def speed() -> float:
    try:
        return max(MIN_SPEED, min(MAX_SPEED, float(get("speed"))))
    except (TypeError, ValueError):
        return 1.0


def prompt_lines() -> str:
    s = load()
    lines = [STYLES.get(s["style"], STYLES["butler"]), LENGTHS.get(s["length"], LENGTHS["normal"])]
    call = str(s["call_me"] or "").strip()
    if call.lower() in ("", "nothing", "none"):
        lines.append("Don't use 'sir' or any title; just talk to him.")
    elif call.lower() != "sir":
        lines.append(f"Address him as '{call}' occasionally, never 'sir'.")
    return " ".join(lines)


def change(key: str, value) -> str:
    s = load()
    key = (key or "").strip().lower().replace(" ", "_")
    if key == "reset":  # voice and personality only; the Settings window's choices stay
        saved = memory._read(FILE, {})
        saved = saved if isinstance(saved, dict) else {}
        memory._write(FILE, {k: v for k, v in saved.items() if k not in s})
        return "All voice and personality settings are back to the defaults."
    if key not in s:
        return f"Unknown setting {key}. Settings: style, length, call_me, speed, voice, offline_voice."
    if key == "style":
        value = str(value).lower().strip()
        if value not in STYLES:
            return f"Unknown style. Choose from: {', '.join(STYLES)}."
    elif key == "length":
        value = str(value).lower().strip()
        if value not in LENGTHS:
            return "Length must be short, normal or long."
    elif key == "speed":
        try:
            value = round(max(MIN_SPEED, min(MAX_SPEED, float(value))), 2)
        except (TypeError, ValueError):
            return f"Speed must be a number from {MIN_SPEED} to {MAX_SPEED} (1 is normal)."
    elif key == "voice":
        voices = getattr(config, "VOICES", {}) or {}
        value = str(value).lower().strip()
        if value not in voices:
            return (f"Unknown voice. Voices set up in config.py: {', '.join(voices) or 'none'}. "
                    "New Fish Audio voices are added to VOICES in config.py.")
    elif key == "offline_voice":
        voices = getattr(config, "OFFLINE_VOICES", {}) or {}
        value = str(value).lower().strip().removesuffix(" voice")
        if value not in voices:
            return f"Unknown offline voice. Choose from: {', '.join(voices)}."
    else:
        value = str(value).strip()[:40]
    saved = memory._read(FILE, {})
    saved = saved if isinstance(saved, dict) else {}
    saved[key] = value
    memory._write(FILE, saved)
    return f"Saved: {key} is now {value}. It applies from the next reply."


def describe() -> str:
    s = load()
    voices = ", ".join(getattr(config, "VOICES", {}) or {}) or "jarvis"
    return (f"Style {s['style']} (options: {', '.join(STYLES)}); length {s['length']} (short, normal, long); "
            f"calls him '{s['call_me']}'; speaking speed {s['speed']} ({MIN_SPEED}-{MAX_SPEED}); "
            f"voice {s['voice']} (available: {voices}); offline voice {s['offline_voice']} "
            f"(available: {', '.join(getattr(config, 'OFFLINE_VOICES', {}) or {})}).")
