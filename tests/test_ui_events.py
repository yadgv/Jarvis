import contextlib

import config
import main
import ui_events


class FakeStream:
    def start(self):
        pass

    def stop(self):
        pass


def test_typed_messages_drive_the_loop(monkeypatch):
    """Typing in the window: no mic recording, Jarvis answers, events reach the window."""
    events, spoken, asked = [], [], []
    monkeypatch.setattr(config, "MODE", "enter")
    monkeypatch.setattr(config, "AUTO_CALIBRATE", False)
    monkeypatch.setattr(ui_events, "gui_active", True)
    monkeypatch.setattr(main, "open_stream", lambda: contextlib.nullcontext(FakeStream()))
    monkeypatch.setattr(main, "speak", spoken.append)
    monkeypatch.setattr(main, "chime", lambda s: None)
    monkeypatch.setattr(main, "record_until_silence", lambda *a: (_ for _ in ()).throw(AssertionError("recorded")))
    monkeypatch.setattr(main, "respond", lambda text, *a: asked.append(text) or False)
    monkeypatch.setattr(ui_events, "_listeners", [])
    ui_events.on(lambda k, t: events.append((k, t)))

    ui_events.inbox.put(("text", "what's on today?"))
    ui_events.inbox.put(("text", "okay, shut down"))
    main.main()

    assert asked == ["what's on today?"]
    assert spoken[-1] == "Powering down. Goodbye, sir."
    assert ("you", "what's on today?") in events
    assert ("status", "idle") in events and events[-1] == ("status", "off")


def test_poll():
    ui_events.inbox.put(("talk", None))
    assert ui_events.poll() == ("talk", None)
    assert ui_events.poll() is None
