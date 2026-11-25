"""News headlines from Google News (free RSS, no key)."""
import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

import config

BASE = "https://news.google.com/rss"
TOPICS = {"world": "WORLD", "business": "BUSINESS", "technology": "TECHNOLOGY", "tech": "TECHNOLOGY",
          "science": "SCIENCE", "sports": "SPORTS", "sport": "SPORTS", "health": "HEALTH",
          "entertainment": "ENTERTAINMENT", "canada": "NATION", "national": "NATION", "local": "NATION"}


def _url(topic):
    hl, gl, ceid = config.NEWS_REGION
    region = f"hl={hl}&gl={gl}&ceid={ceid}"
    topic = (topic or "").strip()
    key = topic.lower()
    if not key or key in ("top", "headlines", "general", "latest"):
        return f"{BASE}?{region}"
    if key in TOPICS:
        return f"{BASE}/headlines/section/topic/{TOPICS[key]}?{region}"
    return f"{BASE}/search?q={quote(topic)}+when:2d&{region}"


def get_news(a):
    count = max(1, min(10, int(a.get("count") or 5)))
    try:
        r = requests.get(_url(a.get("topic")), timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        items = ET.fromstring(r.content).findall("./channel/item")
    except Exception as e:
        return f"Couldn't get the news: {e}"
    lines = []
    for item in items[:count]:
        title = html.unescape(item.findtext("title", "")).strip()
        source = (item.findtext("source", "") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        title = re.sub(r"\s+", " ", title)
        lines.append(f"- {title}" + (f" ({source})" if source else ""))
    return "\n".join(lines) if lines else "No news found for that."


SKILLS = [
    {
        "name": "get_news",
        "description": (
            "Latest news headlines. Optional topic: world, business, technology, science, sports, health, "
            "entertainment, canada, or any search words (e.g. 'Toronto Maple Leafs'). Summarise a few briefly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic or search words; empty for top stories"},
                "count": {"type": "integer", "description": "How many headlines, 1-10 (default 5)"},
            },
        },
        "run": get_news,
    },
]
