"""Jarvis's own pointer: finding things on screen for free and guiding step by step."""
import json
import threading
import time

import pytest

import skills
from skills import browser_bridge, pointer
from tests.test_sight import _post, bridge  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def no_overlay(monkeypatch):
    sent = []
    monkeypatch.setattr(pointer, "send", lambda cmd: sent.append(cmd) or True)
    pointer.guide.update(task="", steps=[], i=0, at=0.0)
    yield sent
    pointer.guide.update(task="", steps=[], i=0, at=0.0)


def test_names_match_what_he_says():
    assert pointer.core("the save button") == "save"
    assert pointer.score("Save", "save") == 1.0
    assert pointer.score("Save As", "save") > pointer.score("Autosave settings for this document", "save")
    assert pointer.score("Insert", "insert tab") > 0.5
    assert pointer.score("Design", "save") == 0
    controls = [("Save", "TextControl", (10, 10, 40, 12)), ("Save", "ButtonControl", (100, 5, 30, 30)),
                ("Save As", "MenuItemControl", (0, 50, 80, 20)), ("Share", "ButtonControl", (200, 5, 30, 30))]
    assert pointer.best_match(controls, "the save button")[2] == (100, 5, 30, 30)     # clickable first
    assert pointer.best_match(controls, "export") is None


def test_ocr_words_spell_the_target():
    words = [(0, "File", 10, 10, 30, 14), (0, "Home", 50, 10, 40, 14), (0, "Insert", 100, 10, 45, 14),
             (1, "Slide", 10, 40, 35, 14), (1, "Number", 50, 40, 55, 14)]
    x, y, w, h, text = pointer.ocr_match(words, "the slide number option")
    assert (x, y, w, h) == (10, 40, 95, 14) and text == "Slide Number"
    assert pointer.ocr_match(words, "design") is None


def test_page_rect_to_screen():
    r = {"x": 100, "y": 50, "w": 80, "h": 20, "dpr": 1.5, "screenX": 0, "screenY": 0,
         "outerWidth": 1280, "outerHeight": 800, "innerWidth": 1264, "innerHeight": 700}
    x, y, w, h = browser_bridge.to_screen(r)
    assert (x, y) == ((8 + 100) * 1.5, (92 + 50) * 1.5) and (w, h) == (120, 30)


def test_extension_finds_on_request(bridge, monkeypatch):  # noqa: F811
    monkeypatch.setattr(browser_bridge, "_last_contact", time.time())
    got = {}
    t = threading.Thread(target=lambda: got.update(browser_bridge.find("sign in", timeout=5) or {}))
    t.start()
    assert _post(bridge, "/next", {})["want"] == "find:sign in"
    _post(bridge, "/found", {"found": True, "x": 10, "y": 20, "w": 60, "h": 24, "label": "sign in", "dpr": 1})
    t.join(5)
    assert got["label"] == "sign in" and got["x"] == 10


def test_point_at(monkeypatch, no_overlay):
    monkeypatch.setattr(pointer, "locate", lambda what: {"x": 5, "y": 6, "w": 7, "h": 8, "name": "Export",
                                                         "how": "ui automation"})
    out = pointer.point_at({"target": "the export button"})
    assert "Pointing at \"Export\"" in out
    assert no_overlay[-1]["cmd"] == "point" and no_overlay[-1]["label"] == "Export" and no_overlay[-1]["x"] == 5
    monkeypatch.setattr(pointer, "locate", lambda what: None)
    assert "couldn't find" in pointer.point_at({"target": "warp drive"})


def test_show_me_how_steps(monkeypatch, no_overlay):
    from brain import llm
    monkeypatch.setattr(pointer, "_visible_controls", lambda hwnd: ["TabItem: Insert", "Button: Header & Footer"])
    from skills import sight
    monkeypatch.setattr(sight, "front_window", lambda: (1, "Deck.pptx - PowerPoint"))
    plan = {"steps": [{"target": "Insert", "say": "Click Insert at the top."},
                      {"target": "Slide Number", "say": "Now click Slide Number."},
                      {"target": "Apply to All", "say": "Then Apply to All."}]}
    seen = {}

    def complete(system, user, max_tokens=400, check=None, **k):
        seen["user"] = user
        check(json.dumps(plan))
        return json.dumps(plan)
    monkeypatch.setattr(llm, "complete", complete)
    found = {"Insert": True, "Slide Number": False, "Apply to All": True}
    monkeypatch.setattr(pointer, "locate", lambda t: {"x": 1, "y": 2, "w": 3, "h": 4, "name": t, "how": "x"}
                        if found.get(t) else None)
    out = pointer.show_me_how({"task": "add slide numbers"})
    assert "Step 1 of 3: Click Insert" in out and "Header & Footer" in seen["user"]
    assert no_overlay[-1]["label"] == "Insert"
    # "next" goes to the guide while it's on, not to the whiteboard
    plan_next = skills.route("next")
    assert plan_next["direct"] == [("guide_next", {})] and "whiteboard_step" in plan_next["exclude"]
    assert "can't see \"Slide Number\"" in pointer.guide_next()
    out = pointer.guide_next()
    assert "Step 3 of 3: Then Apply to All" in out and "last step" in out
    assert skills.route("go back")["direct"] == [("guide_back", {})]
    assert "Step 2 of 3" in pointer.guide_back()


def test_guide_finishes_and_hides(monkeypatch, no_overlay):
    pointer.guide.update(task="t", steps=[{"target": "OK", "say": "Click OK."}], i=0, at=time.time())
    assert "he's done" in pointer.guide_next()
    assert no_overlay[-1] == {"cmd": "hide"} and not pointer.guide_active()
    assert skills.route("next")["direct"] == []       # no guide: "next" is free for the whiteboard


def test_pointer_tools_are_offered():
    for said in ("where's the export button?", "show me how to add page numbers", "which one is the bold button"):
        assert "point_at" in skills.pick_tools(said, limit=10), said
    names = {s["name"] for s in skills.SKILLS}
    assert {"point_at", "show_me_how", "guide_next", "guide_back", "hide_pointer"} <= names


def test_overlay_maths():
    import pointer_overlay as ov
    assert ov.ease(0) == 0 and ov.ease(1) == 1 and 0.4 < ov.ease(0.5) < 0.6
    start, end = (0.0, 0.0), (1000.0, 0.0)
    assert ov.glide_path(start, end, 0) == start and ov.glide_path(start, end, 1) == pytest.approx(end)
    mid = ov.glide_path(start, end, 0.5)
    assert 400 < mid[0] < 600 and abs(mid[1]) > 50            # a gentle arc, not a straight line
    tx, ty = ov.tip_for(100, 100, 200, 40)
    assert 100 < tx < 300 and 100 < ty < 140


def test_show_me_your_pointer(monkeypatch, no_overlay):
    monkeypatch.setattr(pointer, "alive", lambda wait=6.0: True)
    for said in ("show me your pointer", "i dont even see a mouse", "Can you point toward?", "Can you point to my...",
                 "test the pointer"):
        assert skills.route(said)["direct"] == [("test_pointer", {})], said
    out = pointer.test_pointer()
    assert "middle of his screen" in out and no_overlay[-1]["label"] == "Jarvis pointer"
    assert "middle of his screen" in pointer.point_at({})       # nothing named: show it anyway, then ask


def test_pointer_window_that_wont_start_is_reported(monkeypatch, no_overlay):
    monkeypatch.setattr(pointer, "alive", lambda wait=6.0: False)
    pointer._heard[:] = ["error: tkinter isn't installed"]
    assert "didn't start" in pointer.test_pointer() and "tkinter" in pointer.test_pointer()
    assert not any(c["cmd"] == "point" for c in no_overlay)


def test_where_is_the_design_tab_points_not_restyles(monkeypatch):
    from skills import documents
    monkeypatch.setattr(documents, "last", lambda: {"kind": "slides"})
    plan = skills.route("where's the Design tab?")
    assert plan["direct"] == []
    assert "point_at" in skills.pick_tools("where's the Design tab?", limit=10, exclude=tuple(plan["exclude"]))
    assert skills.restyle_intent("make it prettier")


def test_guide_tools_hidden_without_a_guide():
    assert {"guide_next", "guide_back"} <= skills.route("Go back to your own.")["exclude"]


def test_overlay_talks_back(tmp_path):
    import shutil
    import subprocess
    import sys
    py = next((p for p in (sys.executable, shutil.which("python3.12")) if p and subprocess.run(
        [p, "-c", "import tkinter; tkinter.Tk().destroy()"], capture_output=True).returncode == 0), None)
    if not py:
        pytest.skip("no python with tkinter and a display here")
    import os
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pointer_overlay.py")
    cmds = '{"cmd": "ping"}\n{"cmd": "point", "x": "bad"}\n{"cmd": "quit"}\n'
    out = subprocess.run([py, "-u", script], input=cmds, capture_output=True, text=True, timeout=20).stdout
    assert out.startswith("ready:") and "pong" in out and "error:" in out


def test_overlay_drawing_helpers():
    import pointer_overlay as ov
    assert ov.mix("#000000", "#ffffff", 0) == "#000000" and ov.mix("#000000", "#ffffff", 1) == "#ffffff"
    assert ov.mix("#000000", "#ffffff", 0.5) == "#808080"
    assert ov.perimeter(0, 0, 10, 10, 1)[-1] == (0, 0)                   # all the way round
    assert ov.perimeter(0, 0, 10, 10, 0.25)[-1] == (10, 0)               # the top edge
    assert ov.perimeter(0, 0, 10, 10, 0.375)[-1] == (10, 5)
    assert len(ov.rounded(0, 0, 40, 20, 10)) == 24
    assert max(y for _, y in ov.ARROW) < 25                              # small, not clunky
