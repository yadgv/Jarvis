"""Settings he can change by voice ("talk faster", "be more casual", "call me Ziad").
Saved in memory/settings.json; config.py holds the defaults."""
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
    if key == "reset":
        memory._write(FILE, {})
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
