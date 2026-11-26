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


def test_phone_test_command_routes_and_runs(monkeypatch):
    import skills
    from skills import phone
    import telegram_bot
    assert "test_phone_alerts" in skills.pick_tools("test my phone alerts")
    assert "test_phone_alerts" in skills.pick_tools("can you test the call feature")
    monkeypatch.setattr(telegram_bot, "_token", lambda: "x")
    monkeypatch.setattr(telegram_bot, "_allowed", lambda: {1})
    monkeypatch.setattr(phone.config, "CALLMEBOT_USER", "", raising=False)
    sent, asked = [], []
    monkeypatch.setattr(telegram_bot, "ask", lambda q, wait=0: asked.append(q) or True)
    monkeypatch.setattr(telegram_bot, "notify", lambda t: sent.append(t) or True)
    phone._test_run(1)
    assert asked and "Approve" in sent[0]
    out = phone.test_phone()
    assert "CALLMEBOT_USER isn't set" in out
    assert "calls off" in phone.status()


def test_phone_test_without_bot(monkeypatch):
    from skills import phone
    import telegram_bot
    monkeypatch.setattr(telegram_bot, "_token", lambda: "")
    assert "isn't set up" in phone.test_phone()


@pytest.mark.parametrize("said,want", [
    ("Can you brief this article for me?", True),
    ("Could you write me a brief?", True),
    ("Can you breathe this off?", True),
    ("summarize this page", True),
    ("brief me on what I'm reading", True),
    ("give me a brief of my day", False),
    ("brief me on the weather", False),
    ("brief https://example.com/story", False),
    ("what's the weather", False),
])
def test_brief_intent(said, want):
    import skills
    assert skills.brief_intent(said) is want


def test_brief_intent_skips_edits_to_an_open_brief(monkeypatch):
    import skills
    from skills import workspace
    monkeypatch.setitem(workspace._ws, "doc", "# Brief\n")
    assert not skills.brief_intent("can you make the brief shorter and add a summary")
    monkeypatch.setitem(workspace._ws, "doc", "")
    assert skills.brief_intent("write me a brief")


def test_brief_request_runs_the_tool_before_the_model(monkeypatch):
    import skills
    from brain import llm, local_llm, network
    ran, seen = [], {}
    monkeypatch.setattr(network, "online", lambda: True)
    monkeypatch.setattr(local_llm, "should_use", lambda *a, **k: False)
    monkeypatch.setattr(skills, "run", lambda name, args: ran.append(name) or "The brief is on the right half.")

    def fake_chain(asked, system, said, tools_used, exclude=(), history=None, can_ask=True):
        seen.update(asked=asked, exclude=exclude)
        said.append("It's on screen, sir.")
        yield "It's on screen, sir."
    monkeypatch.setattr(llm, "_chain", fake_chain)
    monkeypatch.setattr(llm.auto_memory, "run_in_background", lambda *a: None)
    monkeypatch.setattr(llm.memory, "save_history", lambda h: None)
    out = list(llm.think_stream("Can you brief this article for me?"))
    assert ran == ["brief_document"] and out == ["It's on screen, sir."]
    assert "brief_document -> The brief" in seen["asked"] and "brief_document" in seen["exclude"]


def test_browser_without_extension_falls_back_to_window_text(monkeypatch):
    from skills import browser_bridge, sight, whiteboard, workspace
    monkeypatch.setattr(workspace.sys, "platform", "win32")
    monkeypatch.setattr(whiteboard, "_user32", lambda: None)
    monkeypatch.setattr(workspace, "_windows", lambda u: [(5, "Data breaches are coming fast - CBC News - Brave")])
    monkeypatch.setattr(browser_bridge, "current", lambda hint="": None)
    monkeypatch.setattr(workspace, "_copy_url", lambda u, h: "")
    monkeypatch.setattr(sight, "window_text", lambda h: "Data breaches are coming fast and furious. " * 20)
    monkeypatch.setattr(sight, "ocr_screen", lambda h=None: "")
    src, hwnd = workspace.on_screen()
    assert hwnd == 5 and "furious" in src["text"] and src["name"].startswith("Data breaches")


def test_nothing_readable_says_why(monkeypatch):
    from skills import browser_bridge, sight, whiteboard, workspace
    monkeypatch.setattr(workspace.sys, "platform", "win32")
    monkeypatch.setattr(whiteboard, "_user32", lambda: None)
    monkeypatch.setattr(workspace, "_windows", lambda u: [(5, "Some page - Brave")])
    monkeypatch.setattr(browser_bridge, "current", lambda hint="": None)
    monkeypatch.setattr(workspace, "_copy_url", lambda u, h: "")
    monkeypatch.setattr(sight, "window_text", lambda h: "")
    monkeypatch.setattr(sight, "ocr_screen", lambda h=None: "")
    with pytest.raises(ValueError):
        workspace.on_screen()


def test_no_made_up_briefs_rule():
    import config
    assert "never invent" in config.SYSTEM_PROMPT
