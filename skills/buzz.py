"""whats_the_buzz: what people have been saying about a topic over the last 30 days.

A small, keyless take on last30days-skill by Matt Van Horn
(github.com/mvanhorn/last30days-skill, MIT License, Copyright (c) 2026 Matt
Van Horn). Like it, this asks several communities at once (Hacker News via
Algolia, Reddit, Polymarket betting odds and web news), ranks by engagement,
and leaves the summary to the model. The Hacker News query trick (all words
but the first optional, low-score stories dropped) is from its hackernews.py.

Jarvis says a short summary; the full brief with links goes to Telegram if
the bot is set up."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

DAYS = 30
PER_SOURCE = 6
UA = {"User-Agent": "jarvis-voice-assistant/1.0 (personal use)"}
MIN_HN_POINTS = 5


def _hn(topic):
    since = int(time.time()) - DAYS * 86400
    words = topic.split()
    params = {"query": topic, "tags": "story", "hitsPerPage": PER_SOURCE * 3,
              "numericFilters": f"created_at_i>{since}"}
    if len(words) > 1:
        params["optionalWords"] = " ".join(words[1:])
    r = requests.get("https://hn.algolia.com/api/v1/search", params=params, headers=UA, timeout=10)
    r.raise_for_status()
    hits = [h for h in r.json().get("hits", []) if (h.get("points") or 0) > MIN_HN_POINTS]
    hits.sort(key=lambda h: -(h.get("points") or 0))
    return [{"title": h.get("title", ""), "score": f"{h.get('points', 0)} points, {h.get('num_comments') or 0} comments",
             "link": f"https://news.ycombinator.com/item?id={h.get('objectID')}"} for h in hits[:PER_SOURCE]]


def _reddit(topic):
    r = requests.get("https://www.reddit.com/search.json", headers=UA, timeout=10,
                     params={"q": topic, "t": "month", "sort": "relevance", "limit": PER_SOURCE * 2})
    r.raise_for_status()
    posts = [c.get("data", {}) for c in r.json().get("data", {}).get("children", [])]
    posts.sort(key=lambda p: -((p.get("score") or 0) + 2 * (p.get("num_comments") or 0)))
    return [{"title": f"r/{p.get('subreddit', '?')}: {p.get('title', '')}",
             "score": f"{p.get('score', 0)} upvotes, {p.get('num_comments', 0)} comments",
             "link": "https://www.reddit.com" + p.get("permalink", "")} for p in posts[:PER_SOURCE]]


def _odds(market):
    try:
        outcomes = json.loads(market.get("outcomes") or "[]")
        prices = json.loads(market.get("outcomePrices") or "[]")
        return ", ".join(f"{o} {float(p) * 100:.0f}%" for o, p in zip(outcomes, prices))
    except (ValueError, TypeError):
        return ""


def _polymarket(topic):
    r = requests.get("https://gamma-api.polymarket.com/public-search", headers=UA, timeout=10,
                     params={"q": topic, "limit_per_type": 4, "events_status": "active"})
    r.raise_for_status()
    out = []
    for e in r.json().get("events", [])[:4]:
        markets = sorted(e.get("markets") or [], key=lambda m: -float(m.get("volume") or 0))
        if markets:
            out.append({"title": markets[0].get("question") or e.get("title", ""),
                        "score": f"betting odds: {_odds(markets[0])}",
                        "link": f"https://polymarket.com/event/{e.get('slug', '')}"})
    return out


def _news(topic):
    from skills.web_search import DDGS
    if DDGS is None:
        return []
    found = DDGS().news(topic, timelimit="m", max_results=PER_SOURCE) or []
    return [{"title": f"{n.get('source', '')}: {n.get('title', '')}", "score": n.get("date", "")[:10],
             "link": n.get("url", "")} for n in found]


SOURCES = {"Hacker News": _hn, "Reddit": _reddit, "Polymarket": _polymarket, "News": _news}


def gather(topic):
    """{source: [items]} for every source that answered."""
    results = {}
    with ThreadPoolExecutor(len(SOURCES)) as pool:
        futures = {name: pool.submit(fn, topic) for name, fn in SOURCES.items()}
        for name, f in futures.items():
            try:
                items = f.result(timeout=20)
                if items:
                    results[name] = items
            except Exception as e:
                print(f"[buzz] {name} failed: {e}")
    return results


def brief(topic, results):
    lines = [f"What's the buzz: {topic} (last {DAYS} days)"]
    for name, items in results.items():
        lines.append(f"\n{name}")
        lines += [f"- {i['title']} ({i['score']})\n  {i['link']}" for i in items]
    return "\n".join(lines)


def _send_to_phone(text) -> bool:
    try:
        import telegram_bot
        return telegram_bot.notify(text)
    except Exception as e:
        print(f"[buzz] couldn't send to Telegram: {e}")
        return False


def whats_the_buzz(a):
    topic = (a.get("topic") or "").strip()
    if not topic:
        return "No topic given."
    results = gather(topic)
    if not results:
        return f"Couldn't find any recent discussion of {topic}."
    full = brief(topic, results)
    sent = _send_to_phone(full)
    return (full.replace("\n  http", " http")[:3500]
            + ("\n\n(The full brief with links was sent to his phone on Telegram.)" if sent else ""))


SKILLS = [
    {
        "name": "whats_the_buzz",
        "description": (
            "What people have been saying about a topic over the last 30 days, from Reddit, "
            "Hacker News, Polymarket betting odds and news. Use for 'what's the buzz on X', "
            "'what are people saying about X', 'what's new with X'. Answer in 2-4 spoken sentences: "
            "the main themes, overall mood and any betting odds; no links or usernames."
        ),
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "e.g. 'Claude Code', 'Raptors'"}},
            "required": ["topic"],
        },
        "run": whats_the_buzz,
    },
]
