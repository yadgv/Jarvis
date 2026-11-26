"""The whiteboard: a diagram drawn by a free model, explained step by step."""
import json
import urllib.request

import pytest

import config
from skills import whiteboard as wb

ANSWER = """Sure! Here it is.
TITLE: Servo on an Arduino Uno
```svg
<svg viewBox="0 0 1000 640" xmlns="http://www.w3.org/2000/svg">
  <g id="base"><rect x="50" y="50" width="300" height="200" fill="#0f6f73"/><text x="60" y="80">Arduino Uno</text></g>
  <g id="step-1"><line x1="350" y1="100" x2="600" y2="100" stroke="#ff5a5a" stroke-width="5"/></g>
  <g id="step-2"><line x1="350" y1="140" x2="600" y2="140" stroke="#9aa4b2" stroke-width="5"/></g>
  <g id="step-3" onclick="steal()"><line x1="350" y1="180" x2="600" y2="180" stroke="#ffd23f"/>
    <script>alert(1)</script><a href="javascript:alert(2)"><text>x</text></a></g>
</svg>
```
STEP 1: Connect the servo's red wire to 5V.
STEP 2: Connect the brown wire to GND.
STEP 3: Connect the orange signal wire to pin 9.
"""


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(wb, "_board", {"version": 0, "title": "", "svg": "", "steps": [], "step": 0, "topic": ""})
    opened = []
    monkeypatch.setattr(wb, "open_window", lambda: opened.append(1))
    asked = []

    def complete(system, user, max_tokens=400, small=True, models=None):
        asked.append({"user": user, "models": models, "max_tokens": max_tokens, "small": small})
        return ANSWER
    from brain import llm
    monkeypatch.setattr(llm, "complete", complete)
    return asked, opened


def test_parse_and_clean():
    b = wb.parse(ANSWER)
    assert b["title"] == "Servo on an Arduino Uno"
    assert len(b["steps"]) == 3 and b["steps"][2].endswith("pin 9.")
    assert 'id="step-3"' in b["svg"] and "<rect" in b["svg"]
    for bad in ("<script", "alert(1)", "onclick", "javascript:", "<a ", "</a>", "</script>"):
        assert bad not in b["svg"], bad
    with pytest.raises(ValueError):
        wb.parse("Sorry, I can't draw.")


def test_show_diagram_uses_the_big_free_model(board):
    asked, opened = board
    out = wb.show_diagram({"topic": "wire a servo to my Arduino"})
    assert "step 1 is lit up" in out and "pin 9" in out
    assert asked[0]["models"] == config.WHITEBOARD_MODELS and not asked[0]["small"]
    assert asked[0]["max_tokens"] >= 3000
    assert wb._board["step"] == 1 and wb._board["version"] == 1 and opened


def test_steps_by_voice(board):
    wb.show_diagram({"topic": "servo"})
    assert "Step 2 of 3" in wb.whiteboard_step({"action": "next"})
    assert "Step 3 of 3" in wb.whiteboard_step({"action": "next"})
    assert "last step" in wb.whiteboard_step({"action": "next"})
    assert "Step 2" in wb.whiteboard_step({"action": "back"})
    assert "Step 1" in wb.whiteboard_step({"action": "goto", "step": 1})
    assert "whole drawing" in wb.whiteboard_step({"action": "all"})
    assert "Step 3" in wb.whiteboard_step({"action": "goto", "step": 99})


def test_changes_redraw_from_the_current_drawing(board):
    asked, _ = board
    wb.show_diagram({"topic": "servo"})
    out = wb.show_diagram({"change": "use pin 6 instead"})
    assert out.startswith("Redrawn")
    assert "use pin 6 instead" in asked[1]["user"] and 'id="step-1"' in asked[1]["user"]
    assert wb._board["topic"] == "servo" and wb._board["version"] == 2


def test_empty_board(monkeypatch):
    monkeypatch.setattr(wb, "_board", {"version": 0, "title": "", "svg": "", "steps": [], "step": 0, "topic": ""})
    assert "empty" in wb.whiteboard_step({"action": "next"})


def test_page_is_served_locally_with_a_strict_policy(board, monkeypatch):
    wb.show_diagram({"topic": "servo"})
    base = wb.url()
    assert base.startswith("http://127.0.0.1:")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    page = opener.open(base)
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    assert '<script src="/app.js">' in page.read().decode()
    data = json.loads(opener.open(base + "board.json").read())
    assert data["title"] == "Servo on an Arduino Uno" and data["step"] == 1
    opener.open(base + "step?n=3").read()
    assert wb._board["step"] == 3


def test_needs_internet_to_draw(monkeypatch):
    from brain import network
    import skills
    monkeypatch.setattr(network, "_check", lambda: False)
    monkeypatch.setattr(network, "_state", {"online": None, "until": 0.0})
    assert "internet is down" in skills.run("show_diagram", {"topic": "x"})


def test_picked_for_wiring_questions():
    import skills
    assert "show_diagram" in skills.pick_tools("show me how to wire a servo to my arduino")
