"""use_computer: the computer-use loop, scaling, confirmations and the emergency stop."""
import types

import pytest

import config
from skills import computer


class FakeImg:
    def __init__(self, size=(2560, 1440)):
        self.size = size

    def convert(self, mode):
        return self

    def resize(self, size):
        return FakeImg(size)

    def crop(self, box):
        return FakeImg((box[2] - box[0], box[3] - box[1]))

    def thumbnail(self, size):
        pass

    def save(self, buf, fmt, **options):
        buf.write(b"img")


class FailSafeException(Exception):
    pass


class FakeGui:
    def __init__(self, failsafe_on=None):
        self.calls, self.failsafe_on = [], failsafe_on

    def size(self):
        return (2560, 1440)

    def __getattr__(self, name):
        def record(*a, **k):
            if name == self.failsafe_on:
                raise FailSafeException("corner")
            self.calls.append((name, a, k))
            return (0, 0)
        return record


def block(name, inp=None, id_="t1"):
    return types.SimpleNamespace(type="tool_use", id=id_, name=name, toolset_name="computer", input=inp or {})


def text(t):
    return types.SimpleNamespace(type="text", text=t)


def resp(*content, stop="tool_use"):
    return types.SimpleNamespace(content=list(content), stop_reason=stop)


@pytest.fixture
def env(monkeypatch):
    gui = FakeGui()
    monkeypatch.setattr(computer, "ImageGrab", types.SimpleNamespace(grab=lambda: FakeImg()))
    monkeypatch.setattr(computer, "_gui", lambda: gui)
    monkeypatch.setattr(computer.time, "sleep", lambda s: None)
    monkeypatch.setattr(computer, "_pending", None)
    sent = []

    def script(*responses):
        it = iter(responses)

        def create(**kw):
            sent.append([dict(m) if isinstance(m, dict) else m for m in kw["messages"]])
            assert kw["tools"] == [{"type": "computer_toolset_20260801"}]
            return next(it)
        monkeypatch.setattr(computer.screen, "create", create)
    return gui, sent, script


def test_clicks_are_scaled_back_to_the_real_screen(env):
    gui, sent, script = env
    scr = computer.Screen(gui)
    assert max(scr.w, scr.h) <= 1568 and scr.w * scr.h <= 1_150_000
    script(resp(block("left_click", {"coordinate": [scr.w // 2, scr.h // 2]}), block("type", {"text": "hi"}, "t2")),
           resp(text("Done, sir."), stop="end_turn"))
    out = computer.use_computer({"task": "click the middle"})
    assert out == "Done, sir."
    click = [c for c in gui.calls if c[0] == "click"][0]
    assert abs(click[2]["x"] - 1280) <= 2 and abs(click[2]["y"] - 720) <= 2
    # one result per call, toolset_name echoed, screenshot attached to the last one
    results = sent[1][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert all(r["toolset_name"] == "computer" for r in results)
    assert results[-1]["content"][-1]["type"] == "image"


def test_failure_halts_rest_of_batch(env):
    gui, sent, script = env
    script(resp(block("frobnicate", {}, "a"), block("type", {"text": "x"}, "b")),
           resp(text("Couldn't do it."), stop="end_turn"))
    computer.use_computer({"task": "x"})
    results = sent[1][-1]["content"]
    assert results[0]["is_error"] and results[1]["content"] == computer.HALT
    assert not any(c[0] == "write" for c in gui.calls)


def test_confirmation_pauses_and_resumes(env):
    gui, sent, script = env
    script(resp(text("CONFIRM: send the email to Sam?"), stop="end_turn"),
           resp(text("Sent it."), stop="end_turn"))
    first = computer.use_computer({"task": "email Sam"})
    assert first.startswith("CONFIRM:") and computer._pending
    assert computer.use_computer({"confirmed": True}) == "Sent it."
    assert sent[1][-1] == {"role": "user", "content": "Yes, go ahead."}
    assert computer._pending is None


def test_mouse_in_corner_stops(env, monkeypatch):
    gui, sent, script = env
    gui.failsafe_on = "click"
    script(resp(block("left_click", {"coordinate": [10, 10]})))
    assert "emergency stop" in computer.use_computer({"task": "x"})


def test_step_limit(env, monkeypatch):
    gui, sent, script = env
    monkeypatch.setattr(config, "COMPUTER_MAX_STEPS", 2)
    script(resp(block("screenshot")), resp(block("screenshot")))
    assert "stopped after 2 steps" in computer.use_computer({"task": "x"})


def test_key_names():
    assert computer._keys("ctrl+Return") == ["ctrl", "enter"]
    assert computer._keys("super") == ["win"]


def test_screenshots_sent_as_jpeg(env):
    """PNG screenshots made every step of a long task slower."""
    gui = env[0]
    shot = computer.Screen(gui).screenshot()
    assert shot["source"]["media_type"] == "image/jpeg"
