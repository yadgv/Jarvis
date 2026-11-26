"""Seeing the screen without screenshots: browser extension link, UI text, OCR fallback."""
import json
import os
import re
import threading
import urllib.error
import urllib.request

import pytest

import config
from skills import browser_bridge, sight

EXT = {"Origin": "chrome-extension://abcdefgh", "Content-Type": "application/json"}


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setattr(config, "BROWSER_BRIDGE_PORT", 0)
    monkeypatch.setattr(browser_bridge, "_server", None)
    monkeypatch.setattr(browser_bridge, "_page", {})
    browser_bridge.start()
    port = browser_bridge._server.server_address[1]
    yield f"http://127.0.0.1:{port}"
    browser_bridge._server.shutdown()


def _post(base, path, body, headers=EXT):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


PAGE = {"url": "https://learn.example.edu/thermo/week3", "title": "Week 3: Entropy - Course site",
        "text": "Entropy is a measure of disorder.\n\nThe second law says entropy of an isolated system never decreases. " * 5,
        "selection": "second law"}


def test_only_the_extension_can_post(bridge):
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(bridge, "/page", PAGE, headers={"Content-Type": "application/json"})          # no Origin
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(bridge, "/page", PAGE, headers={"Origin": "https://evil.example", "Content-Type": "application/json"})
    assert e.value.code == 403
    assert _post(bridge, "/page", PAGE)["ok"]
    page = browser_bridge.current()
    assert page["url"] == PAGE["url"] and page["selection"] == "second law"
    assert browser_bridge.current("Week 3: Entropy - Course site - Google Chrome")
    assert browser_bridge.current("Inbox - Gmail - Google Chrome")                        # just reported: still it
    browser_bridge._page["at"] -= browser_bridge.RECENT + 5
    assert browser_bridge.current("Inbox - Gmail - Google Chrome") is None                # older: a different tab
    assert browser_bridge.connected()


def test_page_code_on_request(bridge):
    got = {}
    t = threading.Thread(target=lambda: got.update(browser_bridge.page_code(timeout=5) or {}))
    t.start()
    assert _post(bridge, "/next", {})["want"] == "html"                                  # the extension waiting
    _post(bridge, "/html", {"url": PAGE["url"], "html": "<html><body><h1>Entropy</h1></body></html>"})
    t.join(5)
    assert got["html"].startswith("<html>")


def test_read_screen_uses_the_page_text_and_saves_code(bridge, monkeypatch, tmp_path):
    from skills import files
    monkeypatch.setattr(files, "_folder", lambda name: str(tmp_path))
    monkeypatch.setattr(sight, "front_window", lambda: (7, "Week 3: Entropy - Course site - Google Chrome"))
    monkeypatch.setattr(sight.sys, "platform", "win32")
    _post(bridge, "/page", PAGE)
    monkeypatch.setattr(browser_bridge, "page_code", lambda timeout=8: {"url": PAGE["url"], "html": "<html><body>" +
                        "<img src='data:image/png;base64," + "A" * 500 + "'>" + "<p>x</p></body></html>"})
    out = sight.read_screen({"question": "what's the second law?", "code": True})
    assert "browser extension" in out and "second law says entropy" in out and PAGE["url"] in out
    assert "He has selected" in out and "data:..." in out and "AAAA" not in out
    saved = [f for f in os.listdir(os.path.join(tmp_path, "Jarvis Docs")) if f.endswith("page code.html")]
    assert saved


def test_other_apps_use_ui_text_then_ocr(monkeypatch):
    monkeypatch.setattr(sight.sys, "platform", "win32")
    monkeypatch.setattr(sight, "front_window", lambda: (9, "report.docx - Word"))
    monkeypatch.setattr(sight, "window_text", lambda h: "Results\nThe beam deflected 4.2 mm under 300 N, within the limit set by the design code for the floor.")
    monkeypatch.setattr(sight, "ocr_screen", lambda h: pytest.fail("OCR not needed"))
    assert "UI Automation" in sight.read()["how"]
    monkeypatch.setattr(sight, "window_text", lambda h: "")
    monkeypatch.setattr(sight, "ocr_screen", lambda h: "SUBSCRIBE  12:04 / 30:15  Lecture 7: Fourier series")
    seen = sight.read()
    assert seen["how"] == "Windows OCR" and "Fourier" in seen["text"]


def test_nothing_readable_suggests_the_extension(monkeypatch):
    monkeypatch.setattr(sight.sys, "platform", "win32")
    monkeypatch.setattr(sight, "front_window", lambda: (9, "Some page - Google Chrome"))
    monkeypatch.setattr(browser_bridge, "_page", {})
    monkeypatch.setattr(browser_bridge, "_last_contact", 0.0)
    monkeypatch.setattr(sight, "window_text", lambda h: "")
    monkeypatch.setattr(sight, "ocr_screen", lambda h: "")
    out = sight.read_screen({})
    assert "Load unpacked" in out and "look_at_screen" in out


def test_brief_uses_the_extension_page(bridge, monkeypatch):
    from skills import workspace
    _post(bridge, "/page", PAGE)
    src = workspace._page_source(browser_bridge.current())
    assert src["name"] == "Week 3: Entropy" and "second law" in src["text"] and src["kind"] == "web"


def test_extension_files_match_jarvis():
    folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "browser_extension")
    manifest = json.load(open(os.path.join(folder, "manifest.json")))
    assert manifest["manifest_version"] == 3 and "scripting" in manifest["permissions"]
    bg = open(os.path.join(folder, "background.js")).read()
    assert re.search(r"127\.0\.0\.1:(\d+)", bg).group(1) == str(47321)
    assert config.BROWSER_BRIDGE_PORT == 47321


def test_screen_questions_offer_read_screen_first():
    import skills
    tools = skills.pick_tools("what's on my screen")
    assert "read_screen" in tools
    assert "read_screen" in skills.pick_tools("inspect the code of this page")
