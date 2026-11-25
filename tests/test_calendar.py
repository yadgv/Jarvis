from datetime import date, timedelta

import config
import skills
from skills import calendar_events

TODAY = date.today()
TMRW = TODAY + timedelta(days=1)
ICS = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
DTSTART:{TODAY:%Y%m%d}T140000
DTEND:{TODAY:%Y%m%d}T150000
SUMMARY:Dentist
LOCATION:Main St
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;VALUE=DATE:{TODAY:%Y%m%d}
DTEND;VALUE=DATE:{TMRW:%Y%m%d}
SUMMARY:Mum's birthday
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTART:{TODAY - timedelta(days=7):%Y%m%d}T090000
DTEND:{TODAY - timedelta(days=7):%Y%m%d}T093000
RRULE:FREQ=DAILY
SUMMARY:Standup
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").encode()


class Resp:
    content = ICS

    def raise_for_status(self):
        pass


def setup(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_ICS_URLS", ["https://example.test/basic.ics"])
    monkeypatch.setattr(calendar_events.requests, "get", lambda *a, **k: Resp())
    calendar_events._cache.clear()


def test_today(monkeypatch):
    setup(monkeypatch)
    out = skills.run("get_calendar_events", {"day": "today"})
    assert out.splitlines() == [
        "- all day: Mum's birthday",
        "- 9 AM to 9:30 AM: Standup",
        "- 2 PM to 3 PM: Dentist at Main St",
    ]


def test_several_days_groups_by_day(monkeypatch):
    setup(monkeypatch)
    out = skills.run("get_calendar_events", {"day": "tomorrow", "days": 2})
    assert out.count("Standup") == 2 and "Dentist" not in out
    assert TMRW.strftime("%A %d %B") + ":" in out


def test_not_configured(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_ICS_URLS", [])
    assert "No calendar is connected" in skills.run("get_calendar_events", {})


def test_bad_day(monkeypatch):
    setup(monkeypatch)
    assert "YYYY-MM-DD" in skills.run("get_calendar_events", {"day": "next blursday"})
