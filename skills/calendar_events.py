"""Read your calendar from a private iCal link (read-only, no sign-in setup).

Google Calendar: Settings > (your calendar) > Integrate calendar >
"Secret address in iCal format". Put it in .env as
    CALENDAR_ICS_URLS=https://calendar.google.com/calendar/ical/.../basic.ics
Several calendars: separate the links with spaces. Outlook and iCloud
calendars have the same kind of link (webcal:// links work too).
"""
import time
from datetime import date, datetime, timedelta

import requests

import config

try:
    import icalendar
    import recurring_ical_events
except ImportError:
    icalendar = recurring_ical_events = None

_cache = {}  # url -> (fetched_at, Calendar)
CACHE_SECONDS = 300


def _https(url):
    """Apple and others hand out webcal:// links; they're plain HTTPS underneath."""
    if url.lower().startswith("webcal://"):
        return "https://" + url[len("webcal://"):]
    return url


def _calendars():
    for url in map(_https, config.CALENDAR_ICS_URLS):
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            yield hit[1]
            continue
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.content)
        _cache[url] = (time.time(), cal)
        yield cal


def _parse_day(text):
    text = (text or "today").strip().lower()
    today = date.today()
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(text)


def _local(dt):
    """Event time as a local, timezone-free datetime (all-day events -> midnight)."""
    if not isinstance(dt, datetime):
        return datetime.combine(dt, datetime.min.time())
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def _say_time(dt):
    hour = dt.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{dt.strftime('%M %p')}" if dt.minute else f"{hour} {dt.strftime('%p')}"


def _icloud_signed_in():
    return bool(getattr(config, "ICLOUD_USERNAME", None) and getattr(config, "ICLOUD_APP_PASSWORD", None))


def _sources(start, end):
    """(calendar name, Calendar) pairs. With an iCloud sign-in: every iCloud
    calendar (one per class etc.). Otherwise, or if iCloud fails: the iCal links."""
    if _icloud_signed_in():
        key = ("icloud", start, end)
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        try:
            from skills import icloud_calendar
            found = [(name, icalendar.Calendar.from_ical(text))
                     for name, text in icloud_calendar.read_events(start, end)]
            _cache[key] = (time.time(), found)
            return found
        except Exception as e:
            print(f"[calendar] couldn't read iCloud ({e}); using the iCal link")
    return [("", cal) for cal in _calendars()]


def get_events(a):
    if not config.CALENDAR_ICS_URLS and not _icloud_signed_in():
        return ("No calendar is connected. Tell the user to add CALENDAR_ICS_URLS (their calendar's "
                "secret iCal address) to the .env file.")
    if icalendar is None:
        return "Calendar support isn't installed. Run: pip install icalendar recurring-ical-events"
    try:
        start = _parse_day(a.get("day"))
    except ValueError:
        return "Give the day as today, tomorrow or YYYY-MM-DD."
    days = max(1, min(14, int(a.get("days", 1))))
    end = start + timedelta(days=days)

    events, seen = [], set()
    sources = _sources(start, end)
    several = len({name for name, _ in sources}) > 1
    for cal_name, cal in sources:
        for ev in recurring_ical_events.of(cal).between(start, end):
            begin = ev.get("DTSTART").dt
            finish = ev.get("DTEND").dt if ev.get("DTEND") else begin
            all_day = not isinstance(begin, datetime)
            title = str(ev.get("SUMMARY", "(no title)"))
            if (title, str(begin)) in seen:  # same event from two sources
                continue
            seen.add((title, str(begin)))
            if several and cal_name and cal_name.lower() not in title.lower():
                title = f"{title} ({cal_name})"
            events.append((_local(begin), all_day, _local(finish), title,
                           str(ev.get("LOCATION", "") or "")))
    if not events:
        return f"No events from {start.isoformat()} for {days} day(s)."

    events.sort(key=lambda e: (e[0], not e[1]))
    lines, current = [], None
    for begin, all_day, finish, title, where in events:
        day = begin.date()
        if days > 1 and day != current:
            lines.append(day.strftime("%A %d %B") + ":")
            current = day
        when = "all day" if all_day else f"{_say_time(begin)} to {_say_time(finish)}"
        lines.append(f"- {when}: {title}" + (f" at {where}" if where else ""))
    return "\n".join(lines)


SKILLS = [
    {
        "name": "get_calendar_events",
        "description": (
            "Read the user's calendar (all his calendars, e.g. one per class, with the calendar name "
            "in brackets): what's on today, tomorrow, a given date, or the coming days. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "today, tomorrow, or YYYY-MM-DD (default today)"},
                "days": {"type": "integer", "description": "How many days from that day, 1-14 (default 1)"},
            },
        },
        "run": get_events,
    },
]
