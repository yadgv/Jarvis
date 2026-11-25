"""Add events to your iCloud calendar (CalDAV).

Reading the calendar uses the public iCal link (calendar_events.py); adding
needs a sign-in. Apple doesn't let apps use your real password, so make an
app-specific password:
  appleid.apple.com > Sign-In and Security > App-Specific Passwords > +
and put these in .env:
  ICLOUD_USERNAME=you@icloud.com          (your Apple ID email)
  ICLOUD_APP_PASSWORD=abcd-efgh-ijkl-mnop
  ICLOUD_CALENDAR=Home                    (optional: which calendar; default is the first one)
"""
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

import requests

import config

ROOT = "https://caldav.icloud.com/"
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
_calendar_url = None  # found once per run


def _auth():
    return (config.ICLOUD_USERNAME, config.ICLOUD_APP_PASSWORD)


def _propfind(url, body, depth="0"):
    r = requests.request("PROPFIND", url, data=body.encode(), auth=_auth(), timeout=15,
                         headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"})
    if r.status_code == 401:
        raise PermissionError("iCloud refused the sign-in")
    r.raise_for_status()
    return ET.fromstring(r.content)


def _href(tree, prop):
    el = tree.find(f".//{prop}/d:href", NS)
    if el is None or not (el.text or "").strip():
        raise RuntimeError(f"iCloud didn't say where the calendars are ({prop})")
    return el.text.strip()


def find_calendar():
    """URL of the calendar to add events to (cached)."""
    global _calendar_url
    if _calendar_url:
        return _calendar_url
    tree = _propfind(ROOT, '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>')
    principal = urljoin(ROOT, _href(tree, "d:current-user-principal"))
    tree = _propfind(principal, '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                                '<d:prop><c:calendar-home-set/></d:prop></d:propfind>')
    home = urljoin(principal, _href(tree, "c:calendar-home-set"))
    tree = _propfind(home, '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
                           '<d:displayname/><d:resourcetype/><c:supported-calendar-component-set/>'
                           '</d:prop></d:propfind>', depth="1")
    calendars = []
    for resp in tree.findall("d:response", NS):
        if resp.find(".//d:resourcetype/c:calendar", NS) is None:
            continue
        comps = [c.get("name") for c in resp.findall(".//c:supported-calendar-component-set/c:comp", NS)]
        if comps and "VEVENT" not in comps:
            continue  # a reminders list, not a calendar
        name = (resp.findtext(".//d:displayname", "", NS) or "").strip()
        calendars.append((name, urljoin(home, resp.findtext("d:href", "", NS).strip())))
    if not calendars:
        raise RuntimeError("no calendars found on iCloud")
    wanted = (config.ICLOUD_CALENDAR or "").strip().lower()
    match = [url for name, url in calendars if name.lower() == wanted]
    _calendar_url = match[0] if match else calendars[0][1]
    print(f"[calendar] adding events to {next(n for n, u in calendars if u == _calendar_url) or 'calendar'}")
    return _calendar_url


def _escape(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(title, start, end, all_day=False, location="", uid=None):
    uid = uid or f"{uuid.uuid4()}@jarvis"
    if all_day:
        when = [f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end:%Y%m%d}"]
    else:
        when = [f"DTSTART:{_utc(start)}", f"DTEND:{_utc(end)}"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Jarvis//EN", "BEGIN:VEVENT",
             f"UID:{uid}", f"DTSTAMP:{_utc(datetime.now().astimezone())}", *when,
             f"SUMMARY:{_escape(title)}"]
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n", uid


def _say(dt, all_day):
    if all_day:
        return dt.strftime("%A %d %B") + " (all day)"
    hour = dt.strftime("%I").lstrip("0") or "12"
    return dt.strftime(f"%A %d %B at {hour}:%M %p")


def add_event(a):
    if not (config.ICLOUD_USERNAME and config.ICLOUD_APP_PASSWORD):
        return ("Adding events isn't set up. Tell the user to make an app-specific password at "
                "appleid.apple.com (Sign-In and Security > App-Specific Passwords) and add "
                "ICLOUD_USERNAME and ICLOUD_APP_PASSWORD to the .env file.")
    title = (a.get("title") or "").strip()
    if not title:
        return "No event title given."
    raw = (a.get("start") or "").strip()
    try:
        if len(raw) == 10:  # YYYY-MM-DD: all-day
            start = date.fromisoformat(raw)
            end = start + timedelta(days=max(1, int(a.get("days") or 1)))
            all_day = True
        else:
            start = datetime.fromisoformat(raw)
            if start.tzinfo is None:
                start = start.astimezone()  # his local time
            end = start + timedelta(minutes=max(5, int(a.get("duration_minutes") or 60)))
            all_day = False
    except ValueError:
        return "Give start as YYYY-MM-DDTHH:MM (local time) or YYYY-MM-DD for an all-day event."

    ics, uid = build_ics(title, start, end, all_day, a.get("location") or "")
    try:
        url = urljoin(find_calendar(), uid.split("@")[0] + ".ics")
        r = requests.put(url, data=ics.encode(), auth=_auth(), timeout=15,
                         headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
        if r.status_code == 401:
            raise PermissionError("iCloud refused the sign-in")
        r.raise_for_status()
    except PermissionError:
        return ("iCloud refused the sign-in. The Apple ID email or app-specific password in .env "
                "is wrong (it must be an app-specific password, not the normal one).")
    except Exception as e:
        return f"Couldn't add the event to iCloud: {e}"
    try:  # so "what's on tomorrow" can see it (the public link can still lag a few minutes)
        from skills import calendar_events
        calendar_events._cache.clear()
    except Exception:
        pass
    return f"Added '{title}' on {_say(start, all_day)}."


SKILLS = [
    {
        "name": "add_calendar_event",
        "description": (
            "Add an event to the user's iCloud calendar. Work out the exact date and local time from "
            "what he says (use the current date given in your instructions). Say back the title, day "
            "and time you used."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string",
                          "description": "Local start time YYYY-MM-DDTHH:MM, or YYYY-MM-DD for an all-day event"},
                "duration_minutes": {"type": "integer", "description": "Length in minutes (default 60)"},
                "days": {"type": "integer", "description": "All-day events: how many days (default 1)"},
                "location": {"type": "string"},
            },
            "required": ["title", "start"],
        },
        "run": add_event,
    },
]
