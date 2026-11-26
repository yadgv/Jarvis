"""The basics with no internet.

1. Simple commands are understood right here, with no model at all: the time
   and date, timers, alarms, reminders, volume, play/pause/next, opening apps
   and locking the PC.
2. Anything else goes to the local Ollama model (config.LOCAL_MODEL, or
   OFFLINE_MODEL), with only the tools that work offline.
3. If there's no local model either, Jarvis says briefly that it needs the
   internet.

Speech-to-text (faster-whisper), the wake word (openWakeWord) and the backup
voice (Kokoro/Piper) already run on the PC, so the whole loop works offline."""
import re
import time
from datetime import datetime, timedelta

import config
import skills

# Tools that work with no internet.
OFFLINE_TOOLS = (
    "set_timer", "set_alarm", "list_timers", "cancel_timer",
    "set_reminder", "list_reminders", "cancel_reminder",
    "remember", "forget", "list_jobs", "cancel_job",
    "open_app", "set_volume", "media", "lock_screen", "open_settings", "dark_mode",
    "open_folder", "set_brightness", "app_controls", "start_with_windows",
    "change_setting", "get_settings", "try_offline_voice", "whiteboard_step", "arduino", "shut_down",
)

NEEDS_INTERNET = "I'm offline at the moment, sir, so that one will have to wait for the internet."
BASICS = ("I'm offline at the moment, sir. I can still do the time, timers, alarms, reminders, "
          "volume, music controls and opening apps.")

SYSTEM = (
    "You are Jarvis, a British AI butler, speaking out loud: one or two short sentences, "
    "no lists or markdown. The internet is down, so you only have the tools you're given, "
    "which work offline: timers, alarms, reminders, apps, volume, media keys, settings, memory. "
    "Use them for those requests. If a request needs the internet (weather, news, search, "
    "email, calendar, prices, the screen), say in one short sentence that it needs the "
    "internet and you're offline. Current local date and time: {now}."
)

# ---------- 1. simple commands, no model ----------

_FILLER = re.compile(r"^(?:(?:hey |ok |okay )?jarvis[,.!]?\s*|please\s+|(?:can|could|would|will) you\s+|"
                     r"i want you to\s+|go ahead and\s+)+")
_UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
          "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
          "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}
_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45,
         "fifty": 50, "sixty": 60, "ninety": 90, "a couple of": 2, "a few": 3}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(k) for k in _NUMS), key=len, reverse=True)) + ")"
_DURATION = re.compile(_NUM + r"[\s-]*(" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")\b")


def _clean(text: str) -> str:
    t = re.sub(r"[?!.,]+$", "", (text or "").lower().strip()).strip()
    t = _FILLER.sub("", t)
    return re.sub(r"\s+please$", "", t).strip()


def _num(word: str) -> float:
    return float(word) if word[0].isdigit() else _NUMS[word]


def _seconds(text: str):
    """'5 minutes', '1 hour 30 minutes', 'half an hour', '90 seconds' -> seconds."""
    total = 0
    if re.search(r"\bhalf an? hour\b", text):
        total += 1800
        text = re.sub(r"\bhalf an? hour\b", "", text)
    total += sum(_num(n) * _UNITS[u] for n, u in _DURATION.findall(text))
    if re.search(r"\band a half\b", text) and _DURATION.search(text):
        total += _UNITS[_DURATION.search(text).group(2)] / 2
    return total or None


def _clock(text: str):
    """'7', '7:30', '7 am', '6:45 pm', '18:00' -> (hour, minute), the next time it comes round."""
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?(?=\s|$)", text)
    if not m:
        if re.search(r"\bnoon\b|\bmidday\b", text):
            return 12, 0
        if re.search(r"\bmidnight\b", text):
            return 0, 0
        return None
    hour, minute, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(".", "").replace(" ", "")
    if hour > 23 or minute > 59:
        return None
    if half == "pm" and hour < 12:
        hour += 12
    elif half == "am" and hour == 12:
        hour = 0
    elif not half and hour <= 12:
        # No am/pm: whichever of the two comes next.
        now = datetime.now()
        morning = now.replace(hour=hour % 12, minute=minute, second=0, microsecond=0)
        if morning <= now:
            hour = hour % 12 + 12
            if now.replace(hour=hour, minute=minute, second=0, microsecond=0) <= now:
                hour = hour % 12
        else:
            hour = hour % 12
    return hour, minute


def _say_time(now: datetime) -> str:
    hour = now.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{now.strftime('%M %p')}"


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _timer_label(t: str):
    m = re.search(r"\b(?:for|called|named) (?:the |my |a )?([a-z][a-z ]{1,30})$", t)
    if m and not _DURATION.search(m.group(1)) and not re.search(r"\b(?:hour|minute|second)", m.group(1)):
        return m.group(1).strip()
    return None


def _command(t: str):
    """(tool name, args) or ("say", text) for a simple command, else None."""
    if re.search(r"\bwhat(?:'s| is)? the time\b|\bwhat time is it\b|^time$|\bthe time now\b", t):
        return "say", f"It's {_say_time(datetime.now())}, sir."
    if re.search(r"\bwhat(?:'s| is)? (?:the |today's )?date\b|\bwhat day is (?:it|today)\b|"
                 r"\bwhat(?:'s| is) today\b|\btoday's date\b", t):
        now = datetime.now()
        return "say", f"It's {now.strftime('%A')} the {_ordinal(now.day)} of {now.strftime('%B')}, sir."

    if re.search(r"\b(?:timers?|alarms?)\b", t) and re.search(r"\b(?:cancel|stop|delete|remove|turn off)\b", t):
        return None  # needs to know which one: the model handles it
    if re.search(r"\bhow (?:long|much time)\b.*\btimer\b|\b(?:list|what) (?:are )?(?:my |the )?timers\b", t):
        return "list_timers", {}
    if re.search(r"\btimer\b", t) or re.match(r"(?:set |start )?(?:a )?countdown\b", t):
        seconds = _seconds(t)
        if seconds:
            args = {"seconds": seconds}
            label = _timer_label(t)
            if label:
                args["label"] = label
            return "set_timer", args
        return None
    if re.search(r"\balarm\b|\bwake me(?: up)?\b", t):
        at = _clock(re.sub(r".*?\b(?:at|for)\b", "", t, count=1) if re.search(r"\b(?:at|for)\b", t) else t)
        if at:
            return "set_alarm", {"time": f"{at[0]:02d}:{at[1]:02d}"}
        return None
    m = re.match(r"remind me (?:to |about |that )?(.+)$", t)
    if m:
        rest = m.group(1)
        d = re.search(r"\bin " + _NUM + r"[\s-]*(?:" + "|".join(_UNITS) + r")\b.*?(?=\bto\b|$)|\bin half an hour\b", rest)
        if d:
            what = (rest[:d.start()] + rest[d.end():]).strip()
            what = re.sub(r"^(?:to|about|that)\s+", "", what).strip()
            seconds = _seconds(d.group(0))
            if what and seconds:
                return "set_reminder", {"text": what, "in_minutes": round(seconds / 60, 2)}
        a = re.search(r"\b(?:at)\s+(.+)$", rest)
        if a and _clock(a.group(1)):
            hour, minute = _clock(a.group(1))
            when = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            if re.search(r"\btomorrow\b", rest) or when <= datetime.now():
                when += timedelta(days=1)
            what = re.sub(r"\s*\btomorrow\b", "", rest[:a.start()]).strip()
            if what:
                return "set_reminder", {"text": what, "when": when.strftime("%Y-%m-%dT%H:%M")}
        return None

    if re.search(r"\bunmute\b|\bmute\b", t) and not re.search(r"\bmic", t):
        return "set_volume", {"action": "mute"}
    if re.search(r"\b(?:max(?:imum)?|full) (?:the )?volume\b|\bvolume (?:to |at |all the way )?(?:max(?:imum)?|full|100)\b|"
                 r"\b(?:max|crank) it(?: up)?$", t):
        return "set_volume", {"action": "set", "level": 100}
    if re.search(r"\bhalf (?:the )?volume\b|\bvolume (?:to |at )?half\b", t):
        return "set_volume", {"action": "set", "level": 50}
    level = re.search(r"\bvolume (?:to |at )?(\d{1,3})\b|\b(?:set|put|turn) (?:the )?volume (?:to|at) (\d{1,3})\b", t)
    if level:
        return "set_volume", {"action": "set", "level": min(100, int(level.group(1) or level.group(2)))}
    if re.search(r"\b(?:volume up|turn (?:it|the volume|the music) up|louder|turn up the (?:volume|music)|"
                 r"(?:raise|increase) the volume)\b", t):
        return "set_volume", {"action": "up"}
    if re.search(r"\b(?:volume down|turn (?:it|the volume|the music) down|quieter|softer|"
                 r"turn down the (?:volume|music)|(?:lower|decrease) the volume)\b", t):
        return "set_volume", {"action": "down"}

    if re.fullmatch(r"(?:pause|resume|unpause|play|stop)(?: (?:the )?(?:music|song|track|it|playback))?", t):
        return "media", {"action": "stop" if t.startswith("stop") else "play_pause"}
    if re.fullmatch(r"(?:next|skip)(?: (?:this |the )?(?:song|track|one))?(?: please)?|skip (?:this|it)", t):
        return "media", {"action": "next"}
    if re.fullmatch(r"(?:previous|last|go back)(?: (?:a |the )?(?:song|track|one))?|play the (?:previous|last) (?:song|track)", t):
        return "media", {"action": "previous"}

    if re.fullmatch(r"lock (?:the |my )?(?:screen|computer|pc|laptop)", t):
        return "lock_screen", {}
    m = re.fullmatch(r"(?:open|launch|start|run)(?: up)? (?:the |my )?([a-z0-9][a-z0-9 .+'-]{0,40}?)(?: app| application| program)?"
                     r"(?: for me| now| real quick)?", t)
    if m and not re.search(r"\.(?:com|org|net|ca)\b|\bwebsite\b|\bsite\b|\bfolder\b|\bsettings\b|"
                           r"\btimer\b|\bfile\b", m.group(1)):
        return "open_app", {"name": m.group(1).strip()}
    return None


def quick(text: str):
    """(spoken reply, tool used or None) for a simple command, done with no
    model; None if it isn't one."""
    found = _command(_clean(text))
    if not found:
        return None
    name, args = found
    if name == "say":
        return args, None
    return skills.run(name, args), name


# Questions that can only be answered online. Offline these get an instant
# "needs the internet" instead of a slow trip through the local model.
_ONLINE_ONLY = re.compile(
    r"\b(weather|forecast|temperature outside|rain(ing)?|snow(ing)?|news|headlines?|"
    r"search|google|look (it |that )?up|look up|browse|website|"
    r"e-?mails?|inbox|gmail|calendar|schedule|meetings?|appointments?|"
    r"stocks?|share price|bitcoin|crypto|price of|exchange rate|"
    r"scores?|who won|did .+ win|game (last night|tonight|today)|standings|"
    r"buzz|trending|briefing|latest|"
    r"my screen|on (the|my) screen|look at (the|my|this)|claude code|"
    r"traffic|flights?|deliver(y|ies)|tracking|"
    r"draw|diagram|whiteboard|wiring|wire up)\b")
_OFFLINE_ASKS = re.compile(r"^(remind|set|start|cancel|stop|remember|forget|open|launch|"
                           r"turn|volume|play|pause|skip|lock|mute)\b")


def needs_internet(text: str) -> bool:
    """True when the request clearly needs the internet (weather, news,
    search, email, calendar, prices, scores, the screen, drawing)."""
    t = _clean(text)
    return bool(t) and not _OFFLINE_ASKS.match(t) and bool(_ONLINE_ONLY.search(t))


# ---------- 2. the local model ----------

def model_name() -> str:
    return getattr(config, "LOCAL_MODEL", "") or getattr(config, "OFFLINE_MODEL", "")


def target() -> dict:
    from brain import local_llm
    return {"url": local_llm.URL, "model": model_name(), "who": f"local model {model_name()} (offline)",
            "tools": True, "short_tools": True, "max_tokens": 400,
            # It's on this PC: connecting is instant or not at all. Don't sit
            # waiting on it for a minute if it stalls.
            "timeout": (2, 30)}


def exclude(extra=()) -> tuple:
    """Every tool except the ones that work offline."""
    return tuple(extra) + tuple(s["name"] for s in skills.SKILLS if s["name"] not in OFFLINE_TOOLS)


def system_prompt() -> str:
    now = datetime.now()
    return SYSTEM.format(now=f"{now.strftime('%A %d %B %Y')}, {_say_time(now)}")


_model_off_until = 0.0
MODEL_RETRY_SECONDS = 60


def model_ready() -> bool:
    return bool(model_name()) and time.monotonic() >= _model_off_until


def model_failed(e: Exception):
    global _model_off_until
    _model_off_until = time.monotonic() + MODEL_RETRY_SECONDS
    print(f"[offline] local model {model_name() or '(none)'} didn't answer ({type(e).__name__}: "
          f"{str(e)[:100]}). Is Ollama running? (ollama pull {model_name() or 'llama3.2:3b'})")
