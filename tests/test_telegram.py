"""Phone chat over Telegram: only allowed users, text and voice notes."""
import pytest

import config
import telegram_bot


@pytest.fixture
def bot(monkeypatch):
    calls = []

    def call(method, timeout=15, **params):
        calls.append((method, params))
        if method == "getFile":
            return {"file_path": "voice/file_1.oga"}
        return {}
    monkeypatch.setattr(telegram_bot, "_call", call)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(config, "TELEGRAM_ALLOWED_IDS", "42, 7")
    thought = []
    monkeypatch.setattr(telegram_bot, "_think", lambda text: thought.append(text) or f"Reply to {text}")
    sent = lambda: [p["text"] for m, p in calls if m == "sendMessage"]  # noqa: E731
    return calls, thought, sent


def update(sender, text=None, voice=None, chat_type="private"):
    msg = {"chat": {"id": sender, "type": chat_type}, "from": {"id": sender}}
    if text is not None:
        msg["text"] = text
    if voice:
        msg["voice"] = {"file_id": "f1"}
    return {"update_id": 1, "message": msg}


def test_allowed_user_gets_an_answer(bot):
    calls, thought, sent = bot
    assert telegram_bot.handle(update(42, "what's the weather?")) == "Reply to what's the weather?"
    assert thought == ["what's the weather?"] and sent() == ["Reply to what's the weather?"]


def test_strangers_are_ignored(bot):
    calls, thought, sent = bot
    assert telegram_bot.handle(update(999, "turn off the PC")) is None
    assert not thought and not sent()


def test_first_message_tells_you_your_id(bot, monkeypatch):
    calls, thought, sent = bot
    monkeypatch.setattr(config, "TELEGRAM_ALLOWED_IDS", "")
    telegram_bot.handle(update(555, "hi"))
    assert not thought and "TELEGRAM_ALLOWED_IDS=555" in sent()[0]


def test_voice_notes_are_transcribed(bot, monkeypatch):
    calls, thought, sent = bot
    monkeypatch.setattr(telegram_bot, "_voice_to_text", lambda fid: "set a timer for 5 minutes")
    telegram_bot.handle(update(7, voice=True))
    assert thought == ["set a timer for 5 minutes"]


def test_phone_turns_cant_shut_jarvis_down(monkeypatch):
    from brain import llm
    seen = {}

    def fake(text, followup=False, note="", exclude_tools=()):
        seen.update(note=note, exclude=exclude_tools)
        yield "Okay."
    monkeypatch.setattr(llm, "_think_stream", fake)
    assert telegram_bot._think("shut down") == "Okay."
    assert "shut_down" in seen["exclude"] and "phone" in seen["note"]


def test_long_replies_are_split(bot):
    calls, thought, sent = bot
    telegram_bot.send(42, "x" * 9000)
    assert [len(t) for t in sent()] == [4000, 4000, 1000]


def test_not_started_without_token(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", None)
    assert telegram_bot.start() is False


def test_long_poll_timeout_does_not_clash(monkeypatch):
    """getUpdates sends Telegram a 'timeout' while we also set our own HTTP timeout."""
    import telegram_bot
    seen = {}

    class R:
        def json(self):
            return {"ok": True, "result": []}

    def post(url, json=None, timeout=None):
        seen.update(json=json, timeout=timeout)
        return R()
    monkeypatch.setattr(telegram_bot._session, "post", post)
    assert telegram_bot._call("getUpdates", http_timeout=40, timeout=30) == []
    assert seen == {"json": {"timeout": 30}, "timeout": 40}


def test_offline_pauses_quietly_and_resumes(monkeypatch, capsys):
    from brain import network
    checks = iter([False, False, False, True])
    monkeypatch.setattr(network, "online", lambda: next(checks))
    naps = []
    assert telegram_bot._wait_for_internet(sleep=naps.append)
    out = capsys.readouterr().out
    assert out.count("[telegram]") == 2 and "back online" in out
    assert naps == [telegram_bot.OFFLINE_CHECK_SECONDS] * 2


def test_online_does_not_wait(monkeypatch):
    assert not telegram_bot._wait_for_internet(sleep=lambda s: pytest.fail("waited"))


def test_poll_timeout_while_offline_is_not_logged(monkeypatch):
    import requests
    from brain import network
    monkeypatch.setattr(network, "_check", lambda: False)
    assert telegram_bot._offline_error(requests.ReadTimeout("Read timed out. (read timeout=40)"))
    monkeypatch.setattr(network, "_check", lambda: True)
    assert not telegram_bot._offline_error(requests.ReadTimeout("Read timed out."))
    assert not telegram_bot._offline_error(RuntimeError("Telegram error 409"))


def test_voice_note_decodes_without_faster_whisper_reader(tmp_path):
    """Decode .ogg ourselves: faster-whisper's reader breaks on newer PyAV."""
    av = pytest.importorskip("av")
    import numpy as np
    path = str(tmp_path / "note.ogg")
    with av.open(path, "w") as out:
        stream = out.add_stream("libopus", rate=48000, layout="mono")
        t = np.arange(48000) / 48000
        samples = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
        frame.sample_rate = 48000
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    audio = telegram_bot._decode(path)
    assert audio.dtype == np.float32
    assert 14000 < len(audio) < 18000  # about one second at 16 kHz
    assert 0.1 < np.abs(audio).max() <= 1.0
