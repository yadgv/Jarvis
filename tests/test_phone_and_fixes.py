"""Phone approvals and the fixes from his log: own windows, routing, self-hearing."""
import threading
import time

import pytest

import config
import telegram_bot
import ui_events


def test_jarvis_own_windows_are_skipped():
    from skills import workspace
    wins = [(1, "J.A.R.V.I.S."), (2, "Jarvis brief"), (3, "Thermo notes - Brave")]
    assert workspace.his_window(wins) == (3, "Thermo notes - Brave")
    assert workspace.BROWSERS.search("Thermo notes - Brave")


@pytest.mark.parametrize("said, wanted, not_wanted", [
    ("Just look at the article I have up right now.", {"read_screen", "brief_document"}, {"look_at_screen"}),
    ("Can you brief this?", {"brief_document", "read_screen"}, {"look_at_screen"}),
    ("Can you check the code of this page?", {"read_screen"}, {"look_at_screen"}),
    ("what's in this picture on my screen", {"look_at_screen", "read_screen"}, set()),
])
def test_screen_requests_go_to_the_free_tools(said, wanted, not_wanted):
    import skills
    tools = skills.pick_tools(said)
    assert wanted <= tools and not (not_wanted & tools), (said, tools)


@pytest.fixture
def bot(monkeypatch):
    sent = []

    def call(method, http_timeout=15, **params):
        sent.append((method, params))
        return {"message_id": 77}
    monkeypatch.setattr(telegram_bot, "_call", call)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(config, "TELEGRAM_ALLOWED_IDS", "555")
    monkeypatch.setattr(config, "TELEGRAM_ON", True)
    monkeypatch.setattr(config, "CALLMEBOT_USER", "")
    monkeypatch.setattr(ui_events, "last_you", 0.0)          # he's away
    return sent


def _tap(bot, data, sender=555):
    for _ in range(100):
        if any(m == "sendMessage" and "reply_markup" in p for m, p in bot):
            break
        time.sleep(0.01)
    return telegram_bot.handle_callback({"id": "cb1", "from": {"id": sender}, "data": data,
                                         "message": {"text": "Jarvis needs your OK"}})


def test_approve_on_the_phone(bot):
    from skills import phone
    got = []
    t = threading.Thread(target=lambda: got.append(phone.confirm("send the email to Sam?", wait=5)))
    t.start()
    num = next(iter(telegram_bot._asks)) if telegram_bot._asks else None
    for _ in range(100):
        if telegram_bot._asks:
            num = next(iter(telegram_bot._asks))
            break
        time.sleep(0.01)
    assert _tap(bot, f"ok:{num}", sender=999) is None       # a stranger can't approve
    assert _tap(bot, f"ok:{num}") is True
    t.join(5)
    assert got == [True]
    buttons = [p for m, p in bot if m == "sendMessage"][0]["reply_markup"]["inline_keyboard"][0]
    assert [b["text"] for b in buttons] == ["✅ Approve", "❌ Deny"]
    assert any(m == "editMessageText" and "Approved" in p["text"] for m, p in bot)


def test_deny_and_no_answer(bot):
    from skills import phone
    got = []
    t = threading.Thread(target=lambda: got.append(phone.confirm("delete the old folder?", wait=5)))
    t.start()
    for _ in range(100):
        if telegram_bot._asks:
            break
        time.sleep(0.01)
    _tap(bot, f"no:{next(iter(telegram_bot._asks))}")
    t.join(5)
    assert got == [False]
    assert phone.confirm("anything?", wait=0.05) is None       # nobody tapped in time


def test_only_when_away(bot):
    from skills import phone
    ui_events.emit("you", "open spotify")                       # he's right here
    assert not phone.away() and phone.confirm("x?", wait=0.05) is None and not phone.notify("done")
    ui_events.last_you = 0.0
    assert phone.notify("Sorting Downloads: done") and any(m == "sendMessage" for m, p in bot)


def test_finished_job_goes_to_the_phone_when_away(bot, monkeypatch):
    from skills import background
    task = background.Task("organize_folder", {}, "Sorting Downloads")
    task.state, task.result = "done", "Moved 42 files into 6 folders."
    monkeypatch.setattr(config, "MODE", "wake")
    background._announce(task)
    texts = [p["text"] for m, p in bot if m == "sendMessage"]
    assert texts and "Sorting Downloads" in texts[0] and "42 files" in texts[0]
    ui_events.inbox.get_nowait()                                # it's also told by voice later


def test_risky_screen_step_asks_the_phone_only_in_background(monkeypatch):
    from skills import computer, phone
    monkeypatch.setattr(phone, "confirm", lambda q: q)
    assert computer._ask_phone("CONFIRM: send the message") is None          # spoken turn: ask by voice
    out = []
    t = threading.Thread(target=lambda: out.append(computer._ask_phone("CONFIRM: send the message")), name="task-9")
    t.start()
    t.join()
    assert out == ["send the message"]


def test_his_own_voice_isnt_logged_as_a_wake_word(monkeypatch, capsys):
    import importlib
    import sys
    import types
    oww = types.ModuleType("openwakeword")
    oww.utils = types.SimpleNamespace(download_models=lambda: None)
    mm = types.ModuleType("openwakeword.model")

    class M:
        def __init__(self, **k):
            self.models = {"hey_jarvis": None}
    mm.Model = M
    monkeypatch.setitem(sys.modules, "openwakeword", oww)
    monkeypatch.setitem(sys.modules, "openwakeword.model", mm)
    monkeypatch.delitem(sys.modules, "audio.wakeword", raising=False)
    monkeypatch.setattr(config, "WAKE_VERIFIER", None)
    ww = importlib.import_module("audio.wakeword")
    stt = types.ModuleType("audio.stt")
    stt.transcribe = lambda audio, hints=True: "Certainly, sir."
    monkeypatch.setitem(sys.modules, "audio.stt", stt)
    import numpy as np
    assert ww._heard_name(np.zeros(100, np.int16), quiet=True) is False
    assert "short word heard" not in capsys.readouterr().out
    sys.modules.pop("audio.wakeword", None)
