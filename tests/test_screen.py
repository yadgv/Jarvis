"""look_at_screen: screenshot -> vision model -> short spoken answer."""
import types

import config
from skills import screen


class FakeImage:
    def convert(self, mode):
        return self

    def thumbnail(self, size):
        self.size = size

    def save(self, buf, fmt, **k):
        buf.write(b"jpeg-bytes")


def _fake_client(response, calls):
    def create(**kw):
        calls.append(kw)
        return response
    return types.SimpleNamespace(beta=types.SimpleNamespace(messages=types.SimpleNamespace(create=create)),
                                 messages=types.SimpleNamespace(create=create))


def _resp(text, stop="end_turn"):
    return types.SimpleNamespace(stop_reason=stop, content=[types.SimpleNamespace(type="text", text=text)])


def test_answers_question_about_screen(monkeypatch):
    calls = []
    monkeypatch.setattr(screen, "ImageGrab", types.SimpleNamespace(grab=lambda: FakeImage()))
    monkeypatch.setattr(screen, "_client", _fake_client(_resp("Spotify is open, playing Coldplay."), calls))
    out = screen.look_at_screen({"question": "what's playing?"})
    assert out == "Spotify is open, playing Coldplay."
    sent = calls[0]
    assert sent["model"] == config.SCREEN_MODEL
    blocks = sent["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/jpeg"
    assert blocks[1]["text"] == "what's playing?"


def test_refusal_is_reported(monkeypatch):
    monkeypatch.setattr(screen, "ImageGrab", types.SimpleNamespace(grab=lambda: FakeImage()))
    monkeypatch.setattr(screen, "_client", _fake_client(_resp("", stop="refusal"), []))
    assert "declined" in screen.look_at_screen({})


def test_missing_pillow(monkeypatch):
    monkeypatch.setattr(screen, "ImageGrab", None)
    assert "pip install pillow" in screen.look_at_screen({"question": "x"})


def test_registered():
    import skills
    assert "look_at_screen" in [t["name"] for t in skills.anthropic_tools()]
