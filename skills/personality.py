"""Changing how Jarvis talks, by voice: style, reply length, what he calls you,
speaking speed and voice. Saved in memory/settings.json (see brain/settings.py)."""
from brain import settings


def change_setting(a):
    return settings.change(a.get("setting", ""), a.get("value", ""))


def try_offline_voice(a):
    import config
    name = str(a.get("name") or "").lower().strip().removesuffix(" voice")
    voices = getattr(config, "OFFLINE_VOICES", {}) or {}
    if name not in voices:
        return f"Unknown offline voice. Choose from: {', '.join(voices)}."
    from audio import tts
    return tts.preview(name) + " Ask him if he wants to keep it."


def get_settings(a=None):
    return settings.describe()


SKILLS = [
    {
        "name": "change_setting",
        "description": (
            "Change how you talk when he asks: setting 'style' (butler, casual, brief, formal, playful), "
            "'length' (short, normal, long), 'call_me' (what to call him, e.g. 'Ziad', 'boss', or 'nothing'), "
            "'speed' (speaking speed, 0.7-1.5, 1 is normal; 'a bit faster' is about +0.15), "
            "'voice' (a voice name from get_settings), 'offline_voice' (the voice used with no internet, "
            "a name from get_settings), or 'reset' to go back to the defaults. "
            "Confirm the change in the new style."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "setting": {"type": "string", "enum": ["style", "length", "call_me", "speed", "voice", "offline_voice", "reset"]},
                "value": {"type": "string", "description": "The new value"},
            },
            "required": ["setting"],
        },
        "run": change_setting,
    },
    {
        "name": "try_offline_voice",
        "description": (
            "Play a short sample of one of the offline voices (used when there's no internet) so he can "
            "hear it, e.g. 'let me hear the fable voice'. Names come from get_settings. To keep one, "
            "use change_setting offline_voice."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "offline voice name, e.g. fable"}},
            "required": ["name"],
        },
        "run": try_offline_voice,
    },
    {
        "name": "get_settings",
        "description": "Your current voice and personality settings and the options for each.",
        "parameters": {"type": "object", "properties": {}},
        "run": get_settings,
    },
]
