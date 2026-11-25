"""whats_the_buzz: several sources at once, short reply, full brief to the phone."""
import telegram_bot
from skills import buzz


def test_gathers_sources_and_sends_brief(monkeypatch):
    monkeypatch.setattr(buzz, "SOURCES", {
        "Reddit": lambda t: [{"title": "r/x: Big news", "score": "900 upvotes", "link": "https://r/1"}],
        "Hacker News": lambda t: (_ for _ in ()).throw(RuntimeError("down")),
        "Polymarket": lambda t: [],
    })
    sent = []
    monkeypatch.setattr(telegram_bot, "notify", lambda text: sent.append(text) or True)
    out = buzz.whats_the_buzz({"topic": "Claude"})
    assert "Big news" in out and "sent to his phone" in out
    assert "https://r/1" in sent[0] and "Hacker News" not in sent[0]


def test_nothing_found(monkeypatch):
    monkeypatch.setattr(buzz, "SOURCES", {"Reddit": lambda t: []})
    assert "Couldn't find" in buzz.whats_the_buzz({"topic": "zzz"})


def test_polymarket_odds_parsing():
    m = {"outcomes": '["Yes", "No"]', "outcomePrices": '["0.62", "0.38"]'}
    assert buzz._odds(m) == "Yes 62%, No 38%"


def test_notify_needs_setup(monkeypatch):
    monkeypatch.setattr(telegram_bot.config, "TELEGRAM_BOT_TOKEN", None, raising=False)
    assert telegram_bot.notify("hi") is False
