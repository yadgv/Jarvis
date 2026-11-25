"""Changing how Jarvis talks, by voice: style, reply length, what he calls you,
speaking speed and voice. Saved in memory/settings.json (see brain/settings.py)."""
from brain import settings


def change_setting(a):
    return settings.change(a.get("setting", ""), a.get("value", ""))


def get_settings(a=None):
    return settings.describe()


SKILLS = [
    {
        "name": "change_setting",
        "description": (
            "Change how you talk when he asks: setting 'style' (butler, casual, brief, formal, playful), "
            "'length' (short, normal, long), 'call_me' (what to call him, e.g. 'Ziad', 'boss', or 'nothing'), "
            "'speed' (speaking speed, 0.7-1.5, 1 is normal; 'a bit faster' is about +0.15), "
            "'voice' (a voice name from get_settings), or 'reset' to go back to the defaults. "
            "Confirm the change in the new style."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "setting": {"type": "string", "enum": ["style", "length", "call_me", "speed", "voice", "reset"]},
                "value": {"type": "string", "description": "The new value"},
            },
            "required": ["setting"],
        },
        "run": change_setting,
    },
    {
        "name": "get_settings",
        "description": "Your current voice and personality settings and the options for each.",
        "parameters": {"type": "object", "properties": {}},
        "run": get_settings,
    },
]
