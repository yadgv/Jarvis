"""The whiteboard: a diagram drawn by a free model, explained step by step."""
import json
import urllib.request

import pytest

import config
from skills import whiteboard as wb

ANSWER = """Here you go:
```json
{"title": "Servo on an Arduino Uno", "kind": "wiring",
 "parts": [{"id": "uno", "type": "arduino_uno"}, {"id": "servo", "type": "servo", "label": "SG90 <servo>"}],
 "wires": [{"from": "uno.5V", "to": "servo.V+", "step": 1},
           {"from": "uno.GND", "to": "servo.GND", "step": 2},
           {"from": "uno.pin 9", "to": "servo.SIG", "step": 3, "label": "signal -> PWM"},
           {"from": "uno.D99", "to": "servo.SIG", "step": 3}],
 "steps": ["Connect the servo's red wire to 5V.", "Connect the brown wire to GND.",
           "Connect the orange signal wire to pin 9."]}
```"""


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(wb, "_board", {"version": 0, "title": "", "svg": "", "steps": [], "step": 0, "topic": "",
                                       "spec": None})
    opened = []
    monkeypatch.setattr(wb, "open_window", lambda: opened.append(1))
    asked = []

    def complete(system, user, max_tokens=400, small=True, models=None, check=None):
        asked.append({"user": user, "models": models, "max_tokens": max_tokens, "small": small})
        return ANSWER
    from brain import llm
    monkeypatch.setattr(llm, "complete", complete)
    return asked, opened


def test_parse_and_draw():
    b = wb.parse(ANSWER)
    assert b["title"] == "Servo on an Arduino Uno"
    assert len(b["steps"]) == 3 and b["steps"][2].endswith("pin 9.")
    svg = b["svg"]
    for n in (1, 2, 3):
        assert f'id="step-{n}"' in svg
    assert "Arduino Uno" in svg and "SG90 &lt;servo&gt;" in svg   # text is escaped, never markup
    assert "#e03131" in svg and "#111111" in svg                  # red power, black ground
    assert "→" not in svg and "signal -&gt; PWM" in svg
    assert b["skipped"] == ["uno.D99 -> servo.SIG"]               # a made-up pin is left out
    for bad in ("Sorry, I can't draw.", '{"title": "x"}', "{not json"):
        with pytest.raises(ValueError):
            wb.parse(bad)


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
    assert "use pin 6 instead" in asked[1]["user"] and '"uno.pin 9"' in asked[1]["user"]
    assert wb._board["topic"] == "servo" and wb._board["version"] == 2


def test_empty_board(monkeypatch):
    monkeypatch.setattr(wb, "_board", {"version": 0, "title": "", "svg": "", "steps": [], "step": 0, "topic": ""})
    assert "Nothing has been drawn" in wb.whiteboard_step({"action": "next"})


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


def test_clear_and_close(board):
    wb.show_diagram({"topic": "servo"})
    version = wb._board["version"]
    assert "Cleared" in wb.whiteboard_step({"action": "clear"})
    assert wb._board["svg"] == "" and wb._board["steps"] == [] and wb._board["version"] == version + 1
    assert not wb._board["closed"]
    wb.show_diagram({"topic": "servo"})
    assert "Closed" in wb.whiteboard_step({"action": "close"})
    assert wb._board["closed"] and wb._board["svg"] == ""
    assert not wb._opened  # the next drawing opens a new window


def test_clearing_goes_to_the_tool_not_the_chat_model():
    import skills
    from brain import local_llm, offline
    for text in ("clear the whiteboard", "erase the board", "close the whiteboard", "next step"):
        assert not local_llm.is_easy(text), text
        assert not offline.needs_internet(text), text
    assert "whiteboard_step" in skills.pick_tools("clear the whiteboard")
    assert offline._command("clear the whiteboard") == ("whiteboard_step", {"action": "clear"})
    assert offline._command("wipe the board clean") == ("whiteboard_step", {"action": "clear"})
    assert offline._command("close the whiteboard") == ("whiteboard_step", {"action": "close"})


def test_page_draws_smoothly():
    js = wb.APP_JS
    assert "strokeDashoffset" in js and "sweepIn" in js and "drawStep" in js
    assert "prefers-reduced-motion" in js
    assert "window.close()" in js and "Board clear" in wb.PAGE


@pytest.mark.parametrize("args", [
    {"change": "clear", "topic": "clear"}, {"change": "clear all", "topic": "Arduino Servo and LED Wiring"},
    {"action": "clear"}, {"topic": "clear the whiteboard"}, {"change": "erase the board"},
])
def test_clear_asked_through_show_diagram(board, args):
    # What the model actually sent (from his log).
    asked, _ = board
    wb.show_diagram({"topic": "servo"})
    n = len(asked)
    assert "Cleared" in wb.show_diagram(args)
    assert wb._board["svg"] == "" and len(asked) == n


def test_redraw_that_mentions_clearing_still_draws(board):
    asked, _ = board
    wb.show_diagram({"change": "Clear and redraw full wiring: red lead to 5V", "topic": "servo"})
    assert wb._board["svg"] and asked


def test_reopens_after_he_closes_the_window(monkeypatch):
    launched = []
    monkeypatch.setattr(wb, "_app_browser", lambda: "edge")
    monkeypatch.setattr(wb.subprocess, "Popen", lambda cmd: launched.append(cmd))
    monkeypatch.setattr(wb, "url", lambda: "http://127.0.0.1:1/")
    monkeypatch.setattr(wb, "_opened", False)
    for name in ("_last_seen", "_said_bye", "_launched"):
        monkeypatch.setattr(wb, name, 0.0)
    clock = [1000.0]
    monkeypatch.setattr(wb.time, "monotonic", lambda: clock[0])
    wb.open_window()
    assert len(launched) == 1
    clock[0] += 1; wb._last_seen = clock[0]     # the page is polling
    wb.open_window()
    assert len(launched) == 1                   # still open: no second window
    clock[0] += 1; wb._said_bye = clock[0]      # he closed it with the X: the page says goodbye
    assert not wb.window_open()
    wb.open_window()
    assert len(launched) == 2                   # so it opens again at once
    clock[0] += 2; wb._last_seen = clock[0]     # the new window is polling
    assert wb.window_open()
    clock[0] += 20                              # behind other windows, polls slow down: still open
    assert wb.window_open()
    clock[0] += 80                              # a missed goodbye: long silence counts as closed
    wb.open_window()
    assert len(launched) == 3


def test_open_the_whiteboard(monkeypatch):
    opened = []
    monkeypatch.setattr(wb, "open_window", lambda: opened.append(1))
    from skills import pc_control
    assert "nothing has been drawn" in pc_control.open_app({"name": "whiteboard"})
    assert "nothing has been drawn" in wb.whiteboard_step({"action": "open"})
    assert "nothing has been drawn" in pc_control.open_app({"name": "Microsoft Whiteboard"})
    assert len(opened) == 3


def test_last_drawing_comes_back_after_a_restart_or_clear(board, monkeypatch):
    wb.show_diagram({"topic": "servo"})
    wb.whiteboard_step({"action": "clear"})
    assert "Back on the whiteboard" in wb.whiteboard_step({"action": "draw"})  # what the model sent
    assert wb._board["title"] == "Servo on an Arduino Uno"
    # Jarvis restarted: the board in memory is empty, the saved one isn't.
    monkeypatch.setattr(wb, "_board", {"version": 0, "title": "", "svg": "", "steps": [], "step": 0,
                                       "topic": "", "spec": None, "closed": False})
    assert "Back on the whiteboard" in wb.show_diagram({"action": "open"})
    assert wb._board["svg"] and wb._board["step"] == 1


def test_drawing_never_goes_to_paint_or_microsoft_whiteboard(board):
    from skills import computer
    out = computer.use_computer({"task": "Open Paint and draw a wiring diagram for an Arduino Uno: 1) ..."})
    assert out.startswith("On the whiteboard")
    out = computer.use_computer({"task": "Draw a wiring diagram on the whiteboard for an Arduino Uno"})
    assert out.startswith("On the whiteboard")


def test_board_talk_always_offers_the_whiteboard_tools():
    import skills
    for text in ("Can you draw it on the whiteboard?", "open the whiteboard", "show me how to wire a servo",
                 "can you sketch that", "put it on the board"):
        assert {"show_diagram", "whiteboard_step"} <= skills.pick_tools(text), text
    assert "show_diagram" not in skills.pick_tools("what's the weather")


def test_copied_tool_notes_are_not_spoken():
    from brain import llm
    said = []
    pieces = ["Updating the whiteboard now. ", "[tools used: show_diagram -> On the ", "whiteboard: \"x\". Steps: 1. a"]
    assert list(llm._sentences(iter(pieces), said)) == ["Updating the whiteboard now."]
    assert list(llm._sentences(iter(["[1] is the first pin."]), [])) == ["[1] is the first pin."]


def test_new_topic_starts_on_a_clean_board(board, monkeypatch):
    asked, _ = board
    wiped = []
    real_clear = wb.clear
    monkeypatch.setattr(wb, "clear", lambda close=False: wiped.append(1) or real_clear(close))
    wb.show_diagram({"topic": "servo"})
    assert not wiped                                 # nothing there yet
    wb.show_diagram({"topic": "photosynthesis"})
    assert wiped and "photosynthesis" in asked[-1]["user"] and "servo" not in asked[-1]["user"].lower()[:80]
    wb.show_diagram({"change": "use pin 6"})          # a change keeps the drawing
    assert len(wiped) == 1


@pytest.mark.parametrize("topic", ["how to", "show me how to", "draw it", "that"])
def test_cut_off_request_asks_instead_of_guessing(board, topic):
    asked, _ = board
    out = wb.show_diagram({"topic": topic})
    assert "Ask him what" in out and not asked


def test_change_on_an_empty_board_is_a_new_drawing(board):
    asked, _ = board
    out = wb.show_diagram({"topic": "servo to a breadboard", "change": "signal to pin 9"})
    assert out.startswith("On the whiteboard") and "signal to pin 9" in asked[-1]["user"]


def test_window_title_keeps_the_name_windows_looks_for():
    assert ": '') + 'Jarvis whiteboard'" in wb.APP_JS


def test_see_through_window(monkeypatch):
    calls = []

    class U:
        def GetWindowLongW(self, h, i):
            return 0x100

        def SetWindowLongW(self, h, i, v):
            calls.append(("style", v))

        def SetLayeredWindowAttributes(self, h, key, alpha, flags):
            calls.append(("alpha", alpha))
    wb._see_through(U(), 1, 85)
    assert ("style", 0x100 | 0x80000) in calls and ("alpha", 216) in calls
    calls.clear()
    wb._see_through(U(), 1, 100)                     # solid and never layered: left alone
    assert calls == []
