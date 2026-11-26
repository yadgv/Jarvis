"""Canvas: class files, notes and what's due, using a saved browser sign-in (no tokens)."""
import json
import os
from datetime import datetime, timedelta

import pytest

import config
from skills import canvas, timers

BASE = "https://learn.school.ca"


class Resp:
    def __init__(self, data=None, status=200, links=None, body=b"", text=None):
        self.status_code = status
        self.text = text if text is not None else "while(1);" + json.dumps(data)
        self.links = links or {}
        self.content = body
        self.ok = status < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise canvas.requests.HTTPError(str(self.status_code))

    def iter_content(self, n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, timeout=None, stream=False):
        self.calls.append(url)
        key = url.replace(BASE, "")
        r = self.routes.get(key)
        if r is None:
            return Resp(status=404)
        return r(params) if callable(r) else r


@pytest.fixture
def cv(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path / "mem"))
    monkeypatch.setattr(config, "SCHOOL_FOLDER", str(tmp_path / "School"))
    monkeypatch.setattr(config, "CANVAS_URL", "")
    monkeypatch.setattr(config, "CANVAS_CALENDAR_FEED", "")
    os.makedirs(tmp_path / "mem")
    said = []
    monkeypatch.setattr(timers, "announce", said.append)
    canvas.canvas_setup({"url": "learn.school.ca/courses"})
    return tmp_path


def _use(monkeypatch, routes):
    s = FakeSession(routes)
    monkeypatch.setattr(canvas, "_session", lambda: s)
    return s


def test_setup_keeps_just_the_site(cv):
    assert canvas.base_url() == BASE


def test_never_signed_in_offers_the_window(cv):
    assert "canvas_sign_in" in canvas.canvas_courses()
    assert "canvas_sign_in" in canvas.canvas_download({"course": "thermo"})


def test_cookies_from_the_saved_browser_state(cv):
    os.makedirs(canvas._profile_dir())
    with open(canvas._state_path(), "w") as f:
        json.dump({"cookies": [{"name": "_normandy_session", "value": "abc", "domain": "learn.school.ca",
                                "path": "/"}]}, f)
    s = canvas._session()
    assert s.cookies.get("_normandy_session") == "abc"


def test_pages_are_followed_and_guard_stripped(cv, monkeypatch):
    _use(monkeypatch, {
        "/api/v1/courses": Resp([{"id": 1, "name": "Thermodynamics", "course_code": "MECE 2320"}],
                                links={"next": {"url": BASE + "/api/v1/courses?page=2"}}),
        "/api/v1/courses?page=2": Resp([{"id": 2, "name": "Statics", "course_code": "MECE 2410"}]),
    })
    out = canvas.canvas_courses()
    assert "Thermodynamics (MECE 2320)" in out and "Statics" in out


def test_expired_sign_in(cv, monkeypatch):
    _use(monkeypatch, {"/api/v1/courses": Resp(status=401)})
    assert "canvas_sign_in" in canvas.canvas_courses()
    _use(monkeypatch, {"/api/v1/courses": Resp(text="<html>Log in</html>")})   # sent to the login page
    assert "canvas_sign_in" in canvas.canvas_courses()


BODY = b"First law of thermodynamics. " * 14 + b"Q - W = dU    "


def _class_routes():
    return {
        "/api/v1/courses": Resp([{"id": 7, "name": "Thermodynamics", "course_code": "MECE 2320"},
                                 {"id": 8, "name": "Statics", "course_code": "MECE 2410"}]),
        "/api/v1/courses/7/modules": Resp([
            {"name": "Week 1: Energy", "items": [
                {"type": "File", "content_id": 100}, {"type": "Page", "content_id": 5}]},
            {"name": "Week 2", "items": [{"type": "File", "content_id": 101}]}]),
        "/api/v1/courses/7/files/100": Resp({"id": 100, "display_name": "Lecture 1.txt", "size": len(BODY),
                                             "url": BASE + "/files/100/download"}),
        "/api/v1/courses/7/files/101": Resp({"id": 101, "display_name": "Locked.pdf", "size": 5,
                                             "url": BASE + "/files/101/download", "locked_for_user": True}),
        "/api/v1/courses/7/files": Resp(status=403),   # students often can't open Files
        "/files/100/download": Resp(body=BODY),
    }


def test_download_into_school_folder_and_skip_existing(cv, monkeypatch):
    _use(monkeypatch, _class_routes())
    out = canvas.canvas_download({"course": "thermo"})
    path = cv / "School" / "MECE 2320" / "Week 1 Energy" / "Lecture 1.txt"
    assert path.exists() and path.stat().st_size == len(BODY)
    assert "1 new file downloaded" in out and "notes" in out
    out = canvas.canvas_download({"course": "thermodynamics"})
    assert "0 new files downloaded, 1 already there" in out


def test_unknown_class_lists_them(cv, monkeypatch):
    _use(monkeypatch, _class_routes())
    assert "Statics" in canvas.canvas_download({"course": "chemistry"})


def test_notes_beside_each_file_and_overview(cv, monkeypatch):
    _use(monkeypatch, _class_routes())
    from brain import llm
    asked = []

    def fake(system, user, **k):
        asked.append(user)
        return "First law: energy is conserved.\n- Q - W = dU"
    monkeypatch.setattr(llm, "complete", fake)
    out = canvas.canvas_download({"course": "thermo", "notes": True})
    folder = cv / "School" / "MECE 2320"
    notes = folder / "Week 1 Energy" / "Lecture 1 - notes.md"
    assert notes.exists() and "energy is conserved" in notes.read_text()
    overview = (folder / "MECE 2320 - overview.md").read_text()
    assert "Lecture 1.txt" in overview and "First law" in overview
    assert "study notes for 1 file" in out
    canvas.canvas_download({"course": "thermo", "notes": True})
    assert len(asked) == 1   # notes already up to date: not written again


def test_due_from_calendar_feed(cv, monkeypatch):
    soon = (datetime.now() + timedelta(days=1)).strftime("%Y%m%dT%H%M%S")
    late = (datetime.now() + timedelta(days=30)).strftime("%Y%m%dT%H%M%S")
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
           f"BEGIN:VEVENT\r\nUID:a\r\nDTSTART:{soon}\r\nSUMMARY:Lab 3 report [MECE 2320]\r\nEND:VEVENT\r\n"
           f"BEGIN:VEVENT\r\nUID:b\r\nDTSTART:{late}\r\nSUMMARY:Final project [MECE 2410]\r\nEND:VEVENT\r\n"
           "END:VCALENDAR\r\n").encode()
    monkeypatch.setattr(canvas.requests, "get", lambda url, timeout=None: Resp(body=ics))
    canvas.canvas_setup({"feed": "webcal://learn.school.ca/feeds/calendars/user_x.ics"})
    assert canvas.feed_url().startswith("https://")
    out = canvas.canvas_due({"days": 7})
    assert "Lab 3 report (MECE 2320)" in out and "Final project" not in out
    assert "Lab 3 report" in canvas.briefing_line()


def test_due_from_the_signed_in_api(cv, monkeypatch):
    when = (datetime.now() + timedelta(days=2)).astimezone().isoformat()
    _use(monkeypatch, {
        "/api/v1/users/self/upcoming_events": Resp([{"title": "Quiz 2", "start_at": when, "context_name": "Statics"}]),
        "/api/v1/users/self/todo": Resp([{"assignment": {"name": "HW 4", "due_at": when},
                                          "context_name": "Thermodynamics"}]),
    })
    out = canvas.canvas_due()
    assert "HW 4 (Thermodynamics)" in out and "Quiz 2 (Statics)" in out


def test_briefing_quiet_when_not_set_up(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CANVAS_URL", "")
    monkeypatch.setattr(config, "CANVAS_CALENDAR_FEED", "")
    assert canvas.briefing_line() == ""


def test_sign_in_needs_the_address_first(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CANVAS_URL", "")
    assert "Canvas web address" in canvas.canvas_sign_in()


def test_tools_offered_for_school_requests():
    from skills import pick_tools
    assert "canvas_download" in pick_tools("download my thermo class files from canvas")
    assert "canvas_due" in pick_tools("what assignments are due this week")
