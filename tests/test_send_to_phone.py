"""'Send this to my phone': links, decks, briefs and notes on Telegram."""
import os

import pytest

import skills
import telegram_bot
from skills import phone, sight


@pytest.fixture
def tg(monkeypatch):
    sent = {"text": [], "files": []}
    monkeypatch.setattr(telegram_bot, "_token", lambda: "t")
    monkeypatch.setattr(telegram_bot, "_allowed", lambda: {1})
    monkeypatch.setattr(telegram_bot, "notify", lambda text: sent["text"].append(text) or True)
    monkeypatch.setattr(telegram_bot, "send_file", lambda path, caption="": sent["files"].append(path) or True)
    return sent


def test_routes():
    for said in ("Can you send this link to my phone?", "Can you take the link from the search bar and send it to "
                 "my phone?", "send the slides to my phone", "text me the link", "put the brief on my phone"):
        assert skills.route(said)["direct"][0][0] == "send_to_phone", said
    assert skills.route("Can you test my phone alerts?")["direct"] == [("test_phone_alerts", {})]
    assert skills.route("Can you send a message to my phone?")["direct"] == []
    assert skills.route("send my shopping list to my phone")["direct"] == []      # the model writes it
    assert "send_to_phone" in skills.pick_tools("send my shopping list to my phone", limit=10)


def test_sends_the_link_on_screen(tg, monkeypatch):
    monkeypatch.setattr(sight, "read", lambda want_code=False: {"title": "EMEET speakerphone", "url":
                        "https://www.amazon.ca/dp/B0BVZLS5GZ", "text": "...", "selection": ""})
    out = phone.send_to_phone({"request": "Can you send this link to my phone?"})
    assert "Sent the link" in out and tg["text"] == ["EMEET speakerphone\nhttps://www.amazon.ca/dp/B0BVZLS5GZ"]


def test_no_link_is_not_claimed(tg, monkeypatch):
    monkeypatch.setattr(sight, "read", lambda want_code=False: {"title": "Notepad", "url": "", "text": "hello",
                                                                 "selection": ""})
    assert "couldn't see a web address" in phone.send_to_phone({"what": "link"}) and tg["text"] == []


def test_sends_his_deck_and_notes(tg, monkeypatch, tmp_path):
    from skills import documents
    deck = tmp_path / "Data Breach.pptx"
    deck.write_bytes(b"x")
    monkeypatch.setattr(documents, "find_doc", lambda name="": ({"path": str(deck), "spec": {"title": "Data Breach"}},
                                                                None))
    assert "Sent Data Breach.pptx" in phone.send_to_phone({"request": "send the slides to my phone"})
    assert tg["files"] == [str(deck)]
    assert "Sent it" in phone.send_to_phone({"what": "text", "text": "Milk, eggs, bread"})
    assert tg["text"] == ["Milk, eggs, bread"]


def test_not_set_up_says_so(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_token", lambda: None)
    assert "isn't set up" in phone.send_to_phone({"what": "link"})


def test_send_file_uploads(monkeypatch, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hi")
    posts = []

    class R:
        def json(self):
            return {"ok": True}
    monkeypatch.setattr(telegram_bot, "_token", lambda: "t")
    monkeypatch.setattr(telegram_bot, "_allowed", lambda: {7})
    monkeypatch.setattr(telegram_bot._session, "post", lambda url, **k: posts.append((url, k)) or R())
    assert telegram_bot.send_file(str(f), "cap")
    url, k = posts[0]
    assert url.endswith("/sendDocument") and k["data"]["chat_id"] == 7 and "document" in k["files"]
