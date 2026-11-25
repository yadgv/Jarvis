from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest

import config
from skills import news, reminders, timers

RSS = b"""<?xml version="1.0"?><rss><channel><title>Top stories</title>
<item><title>Leafs win in overtime - TSN</title><source url="https://tsn.ca">TSN</source></item>
<item><title>Rates held &amp; steady - CBC News</title><source url="https://cbc.ca">CBC News</source></item>
<item><title>Third story</title></item>
</channel></rss>"""


def test_news_headlines(monkeypatch):
    urls = []

    def get(url, **k):
        urls.append(url)
        return NS(content=RSS, raise_for_status=lambda: None)
    monkeypatch.setattr(news.requests, "get", get)
    out = news.get_news({"count": 2})
    assert out == "- Leafs win in overtime (TSN)\n- Rates held & steady (CBC News)"
    assert urls[0].startswith("https://news.google.com/rss?hl=en-CA")
    news.get_news({"topic": "Technology"})
    assert "/topic/TECHNOLOGY?" in urls[1]
    news.get_news({"topic": "Maple Leafs"})
    assert "/search?q=Maple%20Leafs" in urls[2]


def test_news_offline():
    assert news.get_news({}).startswith("Couldn't get the news")


@pytest.fixture
def said(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    out = []
    monkeypatch.setattr(timers, "announce", out.append)
    return out


def test_reminder_saved_listed_and_fired(said):
    when = (datetime.now() + timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)
    assert "call mum" in reminders.set_reminder({"text": "call mum", "when": when.strftime("%Y-%m-%dT%H:%M")})
    reminders.set_reminder({"text": "check the oven", "in_minutes": 20})
    listing = reminders.list_reminders()
    assert listing.index("check the oven") < listing.index("call mum")
    assert "6 PM" in listing
    assert reminders.check() == 0 and not said
    assert reminders.check(now=datetime.now() + timedelta(minutes=21)) == 1
    assert said == ["Sir, a reminder: check the oven."]
    # Missed while off: still said, and flagged as late.
    assert reminders.check(now=when + timedelta(hours=3)) == 1
    assert "missed while I was off" in said[-1] and "call mum" in said[-1]
    assert reminders.list_reminders() == "No reminders set."


def test_reminder_cancel_and_errors(said):
    reminders.set_reminder({"text": "bins out", "in_minutes": 60})
    reminders.set_reminder({"text": "gym", "in_minutes": 90})
    assert reminders.cancel_reminder({"text": "bins"}) == "Cancelled 1 reminder."
    assert reminders.cancel_reminder({"text": "all"}) == "Cancelled 1 reminder."
    assert "already passed" in reminders.set_reminder({"text": "x", "when": "2001-01-01T10:00"})
    assert "YYYY-MM-DD" in reminders.set_reminder({"text": "x", "when": "friday"})
