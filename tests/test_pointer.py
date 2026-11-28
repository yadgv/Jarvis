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
    monkeypatch.setattr(pointer, "locate", lambda t, others=True: {"x": 1, "y": 2, "w": 3, "h": 4, "name": t, "how": "x"}
                        if found.get(t) else None)
    out = pointer.show_me_how({"task": "add slide numbers"})
    assert "Step 1 of 3: Click Insert" in out and "Header & Footer" in seen["user"]
    assert no_overlay[-1]["label"] == "1/3  Insert"
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
    assert plan["direct"] == [("point_at", {"target": "Design tab"})]
    assert "restyle_document" not in [n for n, _ in plan["direct"]]
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
    assert max(y for _, y in ov.ARROW) <= 32                             # small, not clunky


def test_point_requests_run_directly():
    for said, want in (("Can you show me where the search bar is?", "search bar"),
                       ("Can you point towards the search bar R?", "search bar"),
                       ("where's the Design tab?", "Design tab"),
                       ("point out the export button on my screen", "export button"),
                       ("Can you point to it?", "it")):
        assert skills.route(said)["direct"] == [("point_at", {"target": want})], said
    assert skills.route("where is my phone")["direct"] == []
    assert skills.route("Can you point to my...")["direct"] == [("test_pointer", {})]


def test_point_to_it_means_the_last_thing(monkeypatch, no_overlay):
    looked = []
    monkeypatch.setattr(pointer, "locate", lambda what: looked.append(what) or None)
    monkeypatch.setattr(pointer, "alive", lambda wait=6.0: True)
    pointer.last_target.update(what="", at=0.0)
    assert "middle of his screen" in pointer.point_at({"target": "it"}) and looked == []
    pointer.point_at({"target": "search bar"})
    pointer.point_at({"target": "it"})
    assert looked == ["search bar", "search bar"]


def test_pointer_takes_jarvis_colour(monkeypatch, no_overlay):
    import pointer_overlay as ov
    monkeypatch.setattr(pointer, "colour", {"now": ""})
    pointer.tint("#f0b95a")                     # the window isn't running: nothing is started for it
    assert no_overlay == []
    pointer.show({"x": 1, "y": 2, "w": 3, "h": 4, "name": "OK"})
    assert no_overlay[-1]["colour"] == "#f0b95a"
    bright, deep, halo = ov.palette("#4fe3ff")
    assert bright != deep != halo and ov.palette("#f0b95a")[0] != bright


def test_his_vs_code_window_is_not_jarvis():
    from skills import workspace
    assert not workspace.is_jarvis_window("jarvis.log - Jarvis Main - Visual Studio Code")
    assert workspace.is_jarvis_window("J.A.R.V.I.S.") and workspace.is_jarvis_window("Jarvis brief")
    assert workspace.is_jarvis_window("Servo · Jarvis 3D viewer")


def test_stage_directions_and_markdown_not_spoken():
    from brain import llm
    said = llm._strip_ignore("(Silence/Wait for confirmation from user that they see the pointer) Now, look to the "
                             "**top left** of your screen.")
    assert said == "Now, look to the top left of your screen."
    assert llm._strip_ignore("Use (for example) a resistor.") == "Use (for example) a resistor."
    assert llm._CLAIM.search("I have drawn up a diagram for wiring an LED strip to your Arduino, sir.")
    assert llm._CLAIM.search("You should find the whiteboard open now.")
    assert not llm._CLAIM.search("You'll see the sun tomorrow.")


def test_how_to_requests_start_a_pointer_guide():
    from skills import _last_howto
    _last_howto.update(task="", at=0.0)
    for said, want in (("ok so show me how to make a new file in this project", "make a new file in this project"),
                       ("Can you show me how to change the numbers on these slides?",
                        "change the numbers on these slides"),
                       ("how do I make a new file in VS Code", "make a new file in VS Code"),
                       ("walk me through turning on dark mode", "turning on dark mode")):
        plan = skills.route(said)
        assert plan["direct"] == [("show_me_how", {"task": want})], said
        assert {"make_file", "use_computer", "point_at", "show_diagram"} <= plan["exclude"]
    for said in ("Can you show me how to wire an LED to an Arduino?", "Can you show me how photosynthesis works?",
                 "how do I get to Toronto", "how do I pronounce this"):
        assert skills.route(said)["direct"] == [], said


def test_use_your_pointer_after_text_steps():
    from skills import _last_howto
    _last_howto.update(task="", at=0.0)
    skills.guide_intent("how do I add slide numbers to this deck")
    assert skills.route("Can you use your pointer?")["direct"] == [("show_me_how", {"task": "add slide numbers to this deck"})]
    assert skills.route("show me how to do it with your pointer")["direct"][0][0] == "show_me_how"
    _last_howto.update(task="", at=0.0)
    assert skills.route("Can you use your pointer?")["direct"] == []


def test_steps_carry_how_he_finishes_them():
    steps = pointer._parse_steps('{"steps": [{"target": "File", "say": "Open File.", "do": "click"},'
                                 '{"target": "Name", "say": "Type a name.", "do": "type"},'
                                 '{"target": "X", "do": "dance"}]}')
    assert [s["do"] for s in steps] == ["click", "type", "click"]


def test_a_click_on_the_target_finishes_the_step(monkeypatch):
    pointer.guide.update(task="t", steps=[{"target": "File", "say": "", "do": "click"}], i=0, at=time.time(), gen=7)
    hit = {"x": 100, "y": 100, "w": 40, "h": 20}
    clicks = iter([(False, False, 0, 0), (True, False, 500, 500), (False, False, 500, 500),   # elsewhere: ignored
                   (True, False, 110, 105), (False, False, 110, 105)])                          # on File: done
    monkeypatch.setattr(pointer, "_mouse", lambda: next(clicks))
    assert pointer.wait_for_step(7, pointer.guide["steps"][0], hit, poll=0)
    keys = iter([False, True, False])
    monkeypatch.setattr(pointer, "_enter_down", lambda: next(keys))
    assert pointer.wait_for_step(7, {"target": "Name", "do": "type"}, hit, poll=0)
    assert not pointer.wait_for_step(8, pointer.guide["steps"][0], hit, poll=0)      # the guide moved on


def test_doing_a_step_moves_the_pointer_and_speaks_the_next(monkeypatch, no_overlay):
    said = []
    monkeypatch.setattr(pointer, "announce", said.append)
    monkeypatch.setattr(pointer, "locate", lambda t, others=True: {"x": 1, "y": 2, "w": 3, "h": 4, "name": t, "how": "x"})
    pointer.guide.update(task="t", steps=[{"target": "File", "say": "Click File.", "do": "click"},
                                          {"target": "New File...", "say": "Now click New File.", "do": "click"}],
                         i=0, at=time.time(), gen=1)
    pointer._auto_next()
    assert said == ["Now click New File."] and no_overlay[-1]["label"] == "2/2  New File..."
    pointer._auto_next()
    assert said[-1] == "That's it, sir. All done." and no_overlay[-1] == {"cmd": "hide"} and not pointer.guide_active()


def test_ocr_skips_jarvis_own_windows():
    words = [(0, "New", 1640, 90, 20, 10), (0, "File", 1662, 90, 20, 10),     # in his text panel
             (1, "New", 200, 300, 20, 10), (1, "File...", 222, 300, 30, 10)]  # the real menu
    mine = [(1500, 0, 1920, 200)]
    kept = [w for w in words if not pointer.covered(w, mine)]
    assert pointer.ocr_match(kept, "New File...")[:2] == (200, 300)


def test_guide_steps_look_only_in_his_window(monkeypatch):
    asked = []
    monkeypatch.setattr(pointer, "locate", lambda what, others=True: asked.append(others) or None)
    monkeypatch.setattr(pointer, "focused_box", lambda: {"x": 1, "y": 2, "w": 50, "h": 20, "name": "box", "how": "focus"})
    assert pointer._find_step({"target": "New File...", "do": "click"}) is None
    assert pointer._find_step({"target": "file name", "do": "type"})["how"] == "focus"   # the box he's typing in
    assert asked == [False, False]


def test_two_watchers_move_on_once(monkeypatch):
    moved = []
    monkeypatch.setattr(pointer, "SETTLE", 0)
    monkeypatch.setattr(pointer, "_auto_next", lambda: moved.append(1))
    pointer.guide.update(task="t", steps=[{"target": "a", "say": "", "do": "type"}], i=0, at=time.time(), gen=3)
    pointer._done(3, pointer.guide["steps"][0])
    pointer._done(3, pointer.guide["steps"][0])
    assert moved == [1]


def test_menu_items_finds_the_client_in_the_inner_module(monkeypatch, capsys):
    """'module uiautomation has no attribute _AutomationClient' (33 times in one evening):
    the class lives in uiautomation.uiautomation, which 'import *' doesn't re-export."""
    import sys
    import types
    from skills import pointer
    item = types.SimpleNamespace(IsOffscreen=False)
    found = types.SimpleNamespace(Length=1, GetElement=lambda i: "el")
    ua = types.SimpleNamespace(CreatePropertyCondition=lambda prop, kind: "cond")
    inner = types.SimpleNamespace(_AutomationClient=types.SimpleNamespace(
        instance=lambda: types.SimpleNamespace(IUIAutomation=ua)))
    fake = types.SimpleNamespace(
        uiautomation=inner, PropertyId=types.SimpleNamespace(ControlTypeProperty=1),
        ControlType=types.SimpleNamespace(MenuItemControl=2), TreeScope=types.SimpleNamespace(Descendants=4),
        Control=types.SimpleNamespace(CreateControlFromElement=lambda el: item))
    monkeypatch.setitem(sys.modules, "uiautomation", fake)
    top = types.SimpleNamespace(Element=types.SimpleNamespace(FindAll=lambda scope, cond: found))
    assert pointer._menu_items(top) == [item]
    # No client at all: one log line, not one per request.
    monkeypatch.setitem(sys.modules, "uiautomation", types.SimpleNamespace())
    monkeypatch.setattr(pointer, "_menu_warned", False)
    assert pointer._menu_items(top) == [] and pointer._menu_items(top) == []
    assert capsys.readouterr().out.count("couldn't list menu items") == 1
