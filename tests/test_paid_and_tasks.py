"""Asking before Claude (it costs money), and long jobs in the background."""
import threading
import time
from types import SimpleNamespace as NS

import pytest

import config
import skills
import ui_events
from brain import paid, settings
from skills import background
from tests.test_cheapest_brain import Resp, brain, says  # noqa: F401  (the fake brain fixture)


class _Final:
    stop_reason, content = "end_turn", []


class _Stream:
    def __init__(self, text):
        self.text_stream = iter([text])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def get_final_message(self):
        return _Final()


@pytest.fixture
def asking(monkeypatch):
    monkeypatch.setattr(config, "ASK_BEFORE_PAID", True)
    monkeypatch.setitem(settings._ORIGINAL, "ASK_BEFORE_PAID", True)
    paid.reset()
    yield
    paid.reset()


def test_asks_before_claude_and_yes_answers_the_old_request(brain, asking, monkeypatch):  # noqa: F811
    used = []
    monkeypatch.setattr(brain.llm, "_client", NS(messages=NS(
        stream=lambda **kw: used.append(kw["messages"][-1]["content"]) or _Stream("Claude here, sir."))))
    brain.replies += [Resp(status=429, error="limit")] * 3
    assert list(brain.llm.think_stream("write me a sonnet")) == [paid.QUESTION]
    assert not used and paid.waiting()
    # yes: straight to Claude (the free ones already failed), with his earlier request
    assert list(brain.llm.think_stream("yes please")) == ["Claude here, sir."]
    assert "write me a sonnet" in used[0] and len(brain.sent) == 3
    paid.answer("and what's the time?")   # the next request
    assert not paid.allowed()              # the yes was for that request only


def test_no_means_no_and_moving_on_drops_the_question(asking):
    paid.asked("write a sonnet")
    assert paid.answer("no thanks") == "no thanks" and not paid.allowed()
    paid.asked("write a sonnet")
    assert paid.answer("what's the weather") == "what's the weather" and not paid.waiting()


def test_yes_always_turns_the_question_off(asking, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    paid.asked(None)
    paid.answer("yes, always use it")
    assert settings.app()["ask_paid"] is False and paid.allowed()


def test_one_off_jobs_raise_instead_of_using_claude(brain, asking, monkeypatch):  # noqa: F811
    monkeypatch.setattr(brain.llm, "_client", NS(messages=NS(create=lambda **k: pytest.fail("used Claude"))))
    monkeypatch.setattr(brain.llm.network, "online", lambda: True)
    brain.replies += [Resp(status=500, error="down")] * 3
    with pytest.raises(paid.PaidNeeded) as e:
        brain.llm.complete("sys", "make a part")
    assert "Only if he says yes" in str(e.value) and paid.waiting()


def test_screen_needs_a_yes(asking, monkeypatch):
    from skills import screen
    monkeypatch.setattr(screen, "_get_client", lambda: pytest.fail("used Claude"))
    with pytest.raises(paid.PaidNeeded):
        screen.create(model="x", messages=[])
    paid.asked(None)
    paid.answer("go ahead")
    calls = []
    monkeypatch.setattr(screen, "_get_client", lambda: NS(beta=NS(messages=NS(create=lambda **k: calls.append(k)))))
    screen.create(model="x", messages=[])
    assert calls


def test_scheduled_jobs_never_ask(brain, asking):  # noqa: F811
    brain.replies += [Resp(status=429, error="limit")] * 3
    with pytest.raises(Exception):
        brain.llm.run_job("check the news")
    assert not paid.waiting()


# ---------- background jobs ----------

@pytest.fixture
def bg(monkeypatch):
    monkeypatch.setattr(config, "BACKGROUND_TASKS", True)
    monkeypatch.setattr(config, "MODE", "wake")
    monkeypatch.setattr(background, "_tasks", {})
    while not ui_events.inbox.empty():
        ui_events.inbox.get_nowait()
    yield
    while not ui_events.inbox.empty():
        ui_events.inbox.get_nowait()


def _wait(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_long_tool_runs_in_the_background_and_reports_back(bg, monkeypatch):
    gate = threading.Event()
    monkeypatch.setitem(skills._BY_NAME, "make_document", {"run": lambda a: gate.wait(2) and "Saved report.docx"})
    skills.set_progress_handler(lambda line: None)   # a live, spoken turn
    try:
        out = skills.run("make_document", {"what": "report"})
    finally:
        skills.set_progress_handler(None)
    assert "Started in the background" in out
    assert "Making the document" in background.list_tasks()
    gate.set()
    assert _wait(lambda: not ui_events.inbox.empty())
    kind, note = ui_events.inbox.get_nowait()
    assert kind == "task_result" and "Saved report.docx" in note
    assert "finished" in background.list_tasks()


def test_not_in_the_background_without_a_live_turn(bg, monkeypatch):
    monkeypatch.setitem(skills._BY_NAME, "make_document", {"run": lambda a: "Saved."})
    assert skills.run("make_document", {}) == "Saved."     # a scheduled job or the phone: wait for it


def test_sort_plan_is_quick_only_the_yes_goes_background(bg):
    assert not background.wants("organize_folder", {"folder": "downloads"}, live=True)
    assert background.wants("organize_folder", {"confirmed": True}, live=True)
    assert not background.wants("use_computer", {"task": "draw the arduino wiring diagram"}, live=True)
    assert background.wants("use_computer", {"task": "open spotify and play jazz"}, live=True)


def test_screen_jobs_queue_and_cancel(bg):
    gate = threading.Event()
    started = []

    def screen_job(a):
        started.append(a["n"])
        gate.wait(2)
        return "done"
    one = background.start("use_computer", {"n": 1}, screen_job, "First screen job")
    two = background.start("use_computer", {"n": 2}, screen_job, "Second screen job")
    assert "queued" in two and "queued" not in one
    assert _wait(lambda: started == [1])
    time.sleep(0.05)
    assert started == [1]                                  # the second waits for the mouse
    assert "waiting for the screen" in background.list_tasks()
    assert "Second screen job" in background.cancel_task({"which": "second"})
    gate.set()
    assert _wait(lambda: not ui_events.inbox.empty())
    time.sleep(0.1)
    assert started == [1]                                  # the cancelled one never ran
    assert "cancelled" in background.list_tasks()


def test_other_jobs_run_side_by_side(bg):
    gate, running = threading.Event(), []
    for n in (1, 2):
        background.start("make_3d_model", {}, lambda a, n=n: running.append(n) or gate.wait(2) or "ok", f"Part {n}")
    assert _wait(lambda: sorted(running) == [1, 2])
    gate.set()


def test_yes_to_claude_carries_into_the_job(bg, asking):
    seen = []
    paid.asked(None)
    paid.answer("yes")
    background.start("make_3d_model", {}, lambda a: seen.append(paid.allowed()) or "ok", "Part")
    assert _wait(lambda: seen == [True])


def test_nothing_to_cancel(bg):
    assert "Nothing is running" in background.cancel_task({})
    assert "Nothing is running" in background.list_tasks()
