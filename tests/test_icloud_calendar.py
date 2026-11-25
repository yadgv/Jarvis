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


@pytest.fixture
def icloud(monkeypatch):
    monkeypatch.setattr(config, "ICLOUD_USERNAME", "z@icloud.com")
    monkeypatch.setattr(config, "ICLOUD_APP_PASSWORD", "abcd-efgh-ijkl-mnop")
    monkeypatch.setattr(config, "ICLOUD_CALENDAR", "work")
    monkeypatch.setattr(ic, "_calendar_url", None)
    calls = []
    answers = {"https://caldav.icloud.com/": PRINCIPAL,
               "https://caldav.icloud.com/123/principal/": HOME,
               "https://p176-caldav.icloud.com:443/123/calendars/": LIST}

    def request(method, url, **kw):
        calls.append((method, url, kw))
        assert kw["auth"] == ("z@icloud.com", "abcd-efgh-ijkl-mnop")
        return NS(status_code=207, content=answers[url], raise_for_status=lambda: None)

    def put(url, **kw):
        calls.append(("PUT", url, kw))
        return NS(status_code=201, raise_for_status=lambda: None)
    monkeypatch.setattr(ic.requests, "request", request)
    monkeypatch.setattr(ic.requests, "put", put)
    return calls


def test_adds_timed_event_to_named_calendar(icloud):
    out = ic.add_event({"title": "Dentist, checkup", "start": "2026-12-03T15:30", "location": "Main St"})
    assert out.startswith("Added 'Dentist, checkup' on Thursday 03 December at 3:30 PM")
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
