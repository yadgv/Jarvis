from datetime import date as date_
from types import SimpleNamespace as NS

import pytest

import config
from skills import icloud_calendar as ic

PRINCIPAL = b"""<?xml version="1.0"?><multistatus xmlns="DAV:"><response><href>/</href><propstat><prop>
<current-user-principal><href>/123/principal/</href></current-user-principal></prop></propstat></response></multistatus>"""
HOME = b"""<?xml version="1.0"?><multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"><response>
<href>/123/principal/</href><propstat><prop><C:calendar-home-set>
<href xmlns="DAV:">https://p176-caldav.icloud.com:443/123/calendars/</href></C:calendar-home-set></prop></propstat>
</response></multistatus>"""
LIST = b"""<?xml version="1.0"?><multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
<response><href>/123/calendars/</href><propstat><prop><resourcetype><collection/></resourcetype></prop></propstat></response>
<response><href>/123/calendars/tasks/</href><propstat><prop><displayname>Reminders</displayname>
<resourcetype><collection/><C:calendar/></resourcetype>
<C:supported-calendar-component-set><C:comp name="VTODO"/></C:supported-calendar-component-set></prop></propstat></response>
<response><href>/123/calendars/home/</href><propstat><prop><displayname>Home</displayname>
<resourcetype><collection/><C:calendar/></resourcetype>
<C:supported-calendar-component-set><C:comp name="VEVENT"/></C:supported-calendar-component-set></prop></propstat></response>
<response><href>/123/calendars/work/</href><propstat><prop><displayname>Work</displayname>
<resourcetype><collection/><C:calendar/></resourcetype>
<C:supported-calendar-component-set><C:comp name="VEVENT"/></C:supported-calendar-component-set></prop></propstat></response>
</multistatus>"""


EMPTY = b'<?xml version="1.0"?><multistatus xmlns="DAV:"></multistatus>'
REPORTS = {}


def _report(summary, day):
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\nBEGIN:VEVENT\r\nUID:" + summary
           + f"\r\nDTSTART:{day:%Y%m%d}T100000\r\nDTEND:{day:%Y%m%d}T110000\r\nSUMMARY:" + summary
           + "\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    return ('<?xml version="1.0"?><multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
            '<response><href>/x.ics</href><propstat><prop><C:calendar-data>' + ics
            + '</C:calendar-data></prop></propstat></response></multistatus>').encode()


@pytest.fixture
def icloud(monkeypatch):
    monkeypatch.setattr(config, "ICLOUD_USERNAME", "z@icloud.com")
    monkeypatch.setattr(config, "ICLOUD_APP_PASSWORD", "abcd-efgh-ijkl-mnop")
    monkeypatch.setattr(config, "ICLOUD_CALENDAR", "work")
    monkeypatch.setattr(ic, "_calendar_url", None)
    monkeypatch.setattr(ic, "_calendars", None)
    calls = []
    answers = {"https://caldav.icloud.com/": PRINCIPAL,
               "https://caldav.icloud.com/123/principal/": HOME,
               "https://p176-caldav.icloud.com:443/123/calendars/": LIST}

    def request(method, url, **kw):
        calls.append((method, url, kw))
        assert kw["auth"] == ("z@icloud.com", "abcd-efgh-ijkl-mnop")
        if method == "DELETE":
            return NS(status_code=204, raise_for_status=lambda: None)
        if method == "REPORT":
            return NS(status_code=207, content=REPORTS.get(url.rstrip("/").rsplit("/", 1)[-1], EMPTY),
                      raise_for_status=lambda: None)
        return NS(status_code=207, content=answers[url], raise_for_status=lambda: None)

    def put(url, **kw):
        calls.append(("PUT", url, kw))
        return NS(status_code=201, raise_for_status=lambda: None)
    monkeypatch.setattr(ic.requests, "request", request)
    monkeypatch.setattr(ic.requests, "put", put)
    return calls


def test_adds_timed_event_to_named_calendar(icloud):
    out = ic.add_event({"title": "Dentist, checkup", "start": "2026-12-03T15:30", "location": "Main St"})
    assert out.startswith("Added 'Dentist, checkup' to the 'Work' calendar on Thursday 03 December at 3:30 PM")
    method, url, kw = icloud[-1]
    assert method == "PUT"
    assert url.startswith("https://p176-caldav.icloud.com:443/123/calendars/work/") and url.endswith(".ics")
    body = kw["data"].decode()
    assert "SUMMARY:Dentist\\, checkup" in body and "LOCATION:Main St" in body
    assert "DTSTART:2026120" in body and body.count("Z\r\n") >= 3
    assert kw["headers"]["If-None-Match"] == "*"
    # Calendar lookup is remembered.
    ic.add_event({"title": "Again", "start": "2026-12-04"})
    assert [c[0] for c in icloud].count("PROPFIND") == 3


def test_all_day_and_default_calendar(icloud, monkeypatch):
    monkeypatch.setattr(config, "ICLOUD_CALENDAR", "")
    out = ic.add_event({"title": "Mum's birthday", "start": "2026-12-25"})
    assert "all day" in out
    url, body = icloud[-1][1], icloud[-1][2]["data"].decode()
    assert "/calendars/home/" in url  # first event calendar, not the reminders list
    assert "DTSTART;VALUE=DATE:20261225" in body and "DTEND;VALUE=DATE:20261226" in body


def test_not_set_up(monkeypatch):
    monkeypatch.setattr(config, "ICLOUD_USERNAME", None)
    assert "app-specific password" in ic.add_event({"title": "x", "start": "2026-12-25"})


def test_bad_password(icloud, monkeypatch):
    monkeypatch.setattr(ic.requests, "request",
                        lambda *a, **k: NS(status_code=401, raise_for_status=lambda: None))
    assert "refused the sign-in" in ic.add_event({"title": "x", "start": "2026-12-25T10:00"})


def test_bad_time(icloud):
    assert "YYYY-MM-DD" in ic.add_event({"title": "x", "start": "next tuesday"})


def test_add_to_a_named_calendar(icloud):
    out = ic.add_event({"title": "Lab", "start": "2026-12-03T10:00", "calendar": "home"})
    assert "'Home' calendar" in out and "/calendars/home/" in icloud[-1][1]
    assert "No calendar called 'Chemistry'" in ic.add_event(
        {"title": "x", "start": "2026-12-03", "calendar": "Chemistry"})


def test_reading_sees_every_calendar(icloud, monkeypatch):
    from datetime import date
    import skills
    from skills import calendar_events
    today = date.today()
    REPORTS.update(home=_report("Gym", today), work=_report("Shift", today))
    monkeypatch.setattr(config, "CALENDAR_ICS_URLS", [])
    calendar_events._cache.clear()
    out = skills.run("get_calendar_events", {"day": "today"})
    assert "Gym (Home)" in out and "Shift (Work)" in out
    REPORTS.clear()


def test_delete_needs_a_yes_in_a_later_turn(icloud, monkeypatch):
    import skills
    monkeypatch.setattr(ic, "_pending_delete", None)
    REPORTS.update(home=_report("Appointment", date_(2026, 11, 26)).replace(
        b"<propstat><prop>", b"<propstat><prop><getetag>\"e1\"</getetag>"))
    monkeypatch.setattr(skills, "turn", 5)
    out = ic.delete_event({"title": "appointment", "date": "2026-11-26"})
    assert out.startswith("Found 'Appointment' on Thursday 26 November at 10:00 AM (Home)")
    assert "Not deleted yet" in ic.delete_event({"confirmed": True})  # same turn
    assert not [c for c in icloud if c[0] == "DELETE"]
    monkeypatch.setattr(skills, "turn", 6)
    assert ic.delete_event({"confirmed": True}).startswith("Deleted 'Appointment'")
    method, url, kw = icloud[-1]
    assert method == "DELETE" and url == "https://p176-caldav.icloud.com:443/x.ics"
    assert kw["headers"] == {"If-Match": '"e1"'}
    assert "Nothing is waiting" in ic.delete_event({"confirmed": True})
    REPORTS.clear()


def test_delete_finds_nothing_or_several(icloud, monkeypatch):
    monkeypatch.setattr(ic, "_pending_delete", None)
    day = date_(2026, 11, 26)
    REPORTS.update(home=_report("Gym", day), work=_report("Gym class", day))
    assert "No single" in ic.delete_event({"title": "dentist", "date": "2026-11-26"})
    assert "More than one match" in ic.delete_event({"title": "gym", "date": "2026-11-26"})
    assert "YYYY-MM-DD" in ic.delete_event({"title": "gym", "date": "tomorrow"})
    REPORTS.clear()
