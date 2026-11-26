"""Smoother animations: what the voice loop tells the orb (task chip, click
ripples) and the whiteboard's own motion."""
import json
import os
import urllib.request

import pytest

import config
import skills
import ui_events
from brain import settings
from skills import whiteboard as wb


@pytest.fixture
def events(monkeypatch):
    got = []
    monkeypatch.setattr(ui_events, "_listeners", [lambda kind, text: got.append((kind, text))])
    return got


def test_task_labels():
    assert skills.task_label("open_app", {"name": "Chrome"}) == "Opening Chrome..."
    assert skills.task_label("organize_folder", {"folder": "downloads"}) == "Sorting downloads..."
    assert skills.task_label("organize_folder", {}) == "Sorting..."      # missing detail: just dropped
    assert skills.task_label("get_time", {}) == ""                        # quick ones show no chip


def test_tool_runs_show_and_finish_a_task(events, monkeypatch):
    monkeypatch.setitem(skills._BY_NAME, "open_app", {"run": lambda a: "Opened Chrome."})
    skills.run("open_app", {"name": "Chrome"})
    assert ("task", {"label": "Opening Chrome...", "step": None, "total": None}) in events
    assert events[-1] == ("task_done", {"ok": True})
    events.clear()
    monkeypatch.setitem(skills._BY_NAME, "open_app", {"run": lambda a: 1 / 0})
    skills.run("open_app", {"name": "Chrome"})
    assert events[-1] == ("task_done", {"ok": False})
    events.clear()
    monkeypatch.setitem(skills._BY_NAME, "get_time", {"run": lambda a: "noon"})
    skills.run("get_time", {})
    assert not [e for e in events if e[0].startswith("task")]


def test_click_ripple_event(events):
    ui_events.click_at(10.4, 20.6)
    assert events == [("click", (10, 20))]


def test_computer_clicks_show_a_ripple(events, monkeypatch):
    from skills import computer
    calls = []
    gui = type("G", (), {"click": lambda self, **k: calls.append(k)})()
    scr = type("S", (), {"real": lambda self, x, y: (x * 2, y * 2)})()
    computer._act(gui, scr, "left_click", {"coordinate": [5, 6]})
    assert ("click", (10, 12)) in events and calls


def test_reduce_motion_setting(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    assert settings.app()["reduce_motion"] is False
    assert wb._calm() is False
    settings.save({"reduce_motion": "true"})
    assert settings.app()["reduce_motion"] is True and wb._calm() is True


def test_board_tells_the_page_to_stay_calm(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    settings.save({"reduce_motion": True})
    base = wb.url()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    assert json.loads(opener.open(base + "board.json").read())["calm"] is True


def test_page_glides_and_fades():
    js, page = wb.APP_JS, wb.PAGE
    assert "function glideTo" in js and "stepView(now)" in js and "requestAnimationFrame" in js
    assert "classList.add('going')" in js            # the old drawing fades out first
    assert "body.calm" in page and "@keyframes enter" in page


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a screen")
def test_widget_animates():  # pragma: no cover - only where Tk has a display
    tk = pytest.importorskip("tkinter")
    import gui
    root = tk.Tk()
    try:
        w = gui.JarvisWidget(root)
        w.start_task({"label": "Moving files", "step": 3, "total": 20})
        assert w.task and w.expanded
        w.finish_task(True)
        assert w.task["done"] and w.task["step"] == 20
        for _ in range(5):
            w.tick()
        assert 0 < w.reveal <= 1
    finally:
        root.destroy()
