"""Morning briefing: weather, today's calendar, reminders and a few headlines.

Jarvis gives it on your first hello of the day ("good morning", "hey Jarvis,
hi"...), and any time you ask for it ("brief me", "what's my day look like").
"""
import re
from datetime import datetime, timedelta

import config
from brain import memory

FILE = "briefing.json"
GREETING = re.compile(
    r"^(?:hey |hi |hello |ok |okay )?(?:jarvis[ ,]*)?"
    r"(good (morning|afternoon|evening|day)|morning|hi|hello|hey|hiya|yo|what'?s up|sup|howdy)"
    r"(?: there)?(?: jarvis| sir)?$")


def _section(name, fn):
    try:
        return f"{name}: {fn()}"
    except Exception as e:
        return f"{name}: unavailable ({e})"


def _reminders_today():
    from skills import reminders
    end = datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time())
    items = [r for r in reminders._load() if datetime.fromisoformat(r["due"]) < end]
    if not items:
        return "none today"
    return "; ".join(f"{reminders._say(datetime.fromisoformat(r['due']))}: {r['text']}"
                     for r in sorted(items, key=lambda r: r["due"]))


def daily_briefing(a=None):
    from skills import calendar_events, news, weather
    mark_briefed()
    parts = [
        _section("Weather", lambda: weather.get_weather({"days": 1})),
        _section("Calendar today", lambda: calendar_events.get_events({"day": "today"})),
        _section("Reminders", _reminders_today),
        _section("Headlines", lambda: news.get_news({"count": config.BRIEFING_HEADLINES})),
    ]
    return ("Give a short spoken briefing from this (under about 45 seconds): greet him for the time of "
            "day, then weather, what's on today, reminders, and two or three headlines in a few words each. "
            "Skip anything unavailable or empty.\n" + "\n".join(parts))


def mark_briefed(day=None):
    memory._write(FILE, {"date": (day or datetime.now().date()).isoformat()})


def is_first_hello(said: str, now=None) -> bool:
    """True for a plain greeting that's the first since BRIEFING_FROM_HOUR today."""
    if not config.MORNING_BRIEFING:
        return False
    now = now or datetime.now()
    if now.hour < config.BRIEFING_FROM_HOUR:
        return False
    if memory._read(FILE, {}).get("date") == now.date().isoformat():
        return False
    return bool(GREETING.match(said.strip()))


NOTE = ("[This is his first hello today. Reply to the greeting, then call daily_briefing and give him "
        "his briefing.]\n")

SKILLS = [
    {
        "name": "daily_briefing",
        "description": ("Get his daily briefing: weather, today's calendar, reminders and top headlines. "
                        "Use for 'brief me', 'what's my day look like', 'morning briefing'."),
        "parameters": {"type": "object", "properties": {}},
        "run": daily_briefing,
    },
]
