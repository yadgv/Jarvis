"""Add events to your iCloud calendar (CalDAV).

Reading the calendar uses the public iCal link (calendar_events.py); adding
needs a sign-in. Apple doesn't let apps use your real password, so make an
app-specific password:
  appleid.apple.com > Sign-In and Security > App-Specific Passwords > +
and put these in .env:
  ICLOUD_USERNAME=you@icloud.com          (your Apple ID email)
  ICLOUD_APP_PASSWORD=abcd-efgh-ijkl-mnop
  ICLOUD_CALENDAR=Home                    (optional: default calendar for new events)
With these set, reading the calendar also uses iCloud, so every calendar
(one per class, work, ...) is seen, not just the one in the iCal link.
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
_calendar_name = ""


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


_calendars = None  # [(name, url)] of event calendars, found once per run
PREFERRED = ("home", "calendar", "personal")


def list_calendars():
    """Every iCloud calendar that holds events, as (name, url). Cached."""
    global _calendars
    if _calendars:
        return _calendars
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
    print(f"[calendar] iCloud calendars: {', '.join(n or '?' for n, _ in calendars)}")
    _calendars = calendars
    return calendars


def _match(calendars, wanted):
    wanted = (wanted or "").strip().lower()
    if not wanted:
        return None
    for exact in (True, False):
        for name, url in calendars:
            if (name.lower() == wanted) if exact else (wanted in name.lower()):
                return name, url
    return None


def find_calendar(name=None):
    """(name, url) of the calendar to add to: the one he named, else
    ICLOUD_CALENDAR, else Home/Calendar/Personal, else the first.
    Raises LookupError if he named one that doesn't exist."""
    global _calendar_url, _calendar_name
    calendars = list_calendars()
    if name:
        hit = _match(calendars, name)
        if not hit:
            raise LookupError(f"No calendar called '{name}'. His calendars: "
                              + ", ".join(n for n, _ in calendars))
        return hit
    if not _calendar_url:
        hit = (_match(calendars, config.ICLOUD_CALENDAR)
               or next(((n, u) for n, u in calendars if n.lower() in PREFERRED), None)
               or calendars[0])
        _calendar_name, _calendar_url = hit
        print(f"[calendar] adding events to {_calendar_name or 'calendar'} "
              "(set ICLOUD_CALENDAR in .env to pick)")
    return _calendar_name, _calendar_url


def _report(url, start, end):
    return [ics for _, _, ics in _report_items(url, start, end)]


def _report_items(url, start, end):
    """(href, etag, ics text) for each event between two UTC times."""
    body = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            '<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
            '<c:comp-filter name="VEVENT">'
            f'<c:time-range start="{start:%Y%m%dT%H%M%SZ}" end="{end:%Y%m%dT%H%M%SZ}"/>'
            '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    r = requests.request("REPORT", url, data=body.encode(), auth=_auth(), timeout=15,
                         headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
    if r.status_code == 401:
        raise PermissionError("iCloud refused the sign-in")
    r.raise_for_status()
    out = []
    for resp in ET.fromstring(r.content).findall("d:response", NS):
        ics = resp.findtext(".//c:calendar-data", "", NS)
        if ics and ics.strip():
            out.append((urljoin(url, resp.findtext("d:href", "", NS).strip()),
                        (resp.findtext(".//d:getetag", "", NS) or "").strip(), ics))
    return out


def read_events(start, end):
    """Raw iCalendar texts of events between two dates, from every calendar,
    as (calendar name, ics text). Used by get_calendar_events."""
    t0 = datetime.combine(start, datetime.min.time()).astimezone(timezone.utc) - timedelta(days=1)
    t1 = datetime.combine(end, datetime.min.time()).astimezone(timezone.utc) + timedelta(days=1)
    out = []
    for name, url in list_calendars():
        for text in _report(url, t0, t1):
            out.append((name, text))
    return out


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
        cal_name, cal_url = find_calendar(a.get("calendar"))
        url = urljoin(cal_url, uid.split("@")[0] + ".ics")
        r = requests.put(url, data=ics.encode(), auth=_auth(), timeout=15,
                         headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
        if r.status_code == 401:
            raise PermissionError("iCloud refused the sign-in")
        r.raise_for_status()
    except LookupError as e:
        return str(e)
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
    where = f" to the '{cal_name}' calendar" if cal_name else ""
    return f"Added '{title}'{where} on {_say(start, all_day)}."


_pending_delete = None  # (href, etag, description, turn asked)


def _field(ics, name):
    """Value of the first NAME (or NAME;params) line inside the VEVENT."""
    body = ics.split("BEGIN:VEVENT", 1)[-1].replace("\r\n ", "").replace("\n ", "")
    for line in body.splitlines():
        key, _, value = line.partition(":")
        if key.split(";")[0].upper() == name:
            return value.strip()
    return ""


def _start(ics):
    """(local datetime or date, all_day) of the event's DTSTART."""
    raw = _field(ics, "DTSTART")
    if len(raw) == 8:
        return datetime.strptime(raw, "%Y%m%d").date(), True
    dt = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
    if raw.endswith("Z"):
        dt = dt.replace(tzinfo=timezone.utc).astimezone()
    return dt, False


def delete_event(a):
    """Two steps, because a deleted event can't be brought back: the first call
    finds the event and asks; a later turn with confirmed=true deletes it."""
    global _pending_delete
    import skills  # the package, for its turn counter (imported late: it imports us)
    if not (config.ICLOUD_USERNAME and config.ICLOUD_APP_PASSWORD):
        return "Deleting events needs the iCloud sign-in (ICLOUD_USERNAME and ICLOUD_APP_PASSWORD in .env)."
    try:
        if a.get("confirmed"):
            if _pending_delete is None:
                return "Nothing is waiting to be deleted. Find the event first (without confirmed)."
            href, etag, what, asked = _pending_delete
            if skills.turn <= asked:
                return f"Not deleted yet: ask him first whether to delete {what}, and wait for a yes."
            headers = {"If-Match": etag} if etag else {}
            r = requests.request("DELETE", href, auth=_auth(), timeout=15, headers=headers)
            if r.status_code == 401:
                raise PermissionError("iCloud refused the sign-in")
            if r.status_code == 412:
                _pending_delete = None
                return "That event changed since I found it, so I didn't delete it. Ask again."
            r.raise_for_status()
            _pending_delete = None
            try:
                from skills import calendar_events
                calendar_events._cache.clear()
            except Exception:
                pass
            return f"Deleted {what}."

        title = (a.get("title") or "").strip().lower()
        try:
            day = date.fromisoformat((a.get("date") or "").strip()[:10])
        except ValueError:
            return "Give the event's date as YYYY-MM-DD."
        t0 = datetime.combine(day, datetime.min.time()).astimezone(timezone.utc)
        t1 = t0 + timedelta(days=1)
        calendars = [find_calendar(a["calendar"])] if a.get("calendar") else list_calendars()
        found = []
        for cal_name, url in calendars:
            for href, etag, ics in _report_items(url, t0, t1):
                summary = _field(ics, "SUMMARY").replace("\\,", ",").replace("\\;", ";")
                if title and title not in summary.lower():
                    continue
                if _field(ics, "RRULE"):
                    continue  # a repeating event: deleting the file would remove every one
                when, all_day = _start(ics)
                if (when if all_day else when.date()) != day:
                    continue
                found.append((href, etag, f"'{summary}' on {_say(when, all_day)} ({cal_name})"))
    except LookupError as e:
        return str(e)
    except PermissionError:
        return "iCloud refused the sign-in. The app-specific password in .env is wrong."
    except Exception as e:
        return f"Couldn't reach iCloud: {e}"
    if not found:
        return f"No single (non-repeating) event matching '{a.get('title') or ''}' on {day:%A %d %B}."
    if len(found) > 1:
        return "More than one match; ask which: " + "; ".join(f[2] for f in found)
    _pending_delete = (*found[0], skills.turn)
    return (f"Found {found[0][2]}. Ask him to confirm, then call delete_calendar_event again with "
            "confirmed=true.")


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
                "calendar": {"type": "string",
                             "description": "Which of his calendars, if he names one (e.g. a class); default his main one"},
            },
            "required": ["title", "start"],
        },
        "run": add_event,
    },
    {
        "name": "delete_calendar_event",
        "description": (
            "Delete (cancel, remove, get rid of) one event from his iCloud calendar. First call with the "
            "title and date: it finds the event. Read it back and ask him to confirm; only after he says "
            "yes, call again with confirmed=true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Words from the event's title, e.g. 'Appointment'"},
                "date": {"type": "string", "description": "The event's local date, YYYY-MM-DD"},
                "calendar": {"type": "string", "description": "Which calendar, if he names one"},
                "confirmed": {"type": "boolean", "description": "He said yes to deleting the event found"},
            },
        },
        "run": delete_event,
    },
]
