"""Web search through DuckDuckGo (free, no API key).

Uses the `ddgs` package when it's installed and working, otherwise falls back
to DuckDuckGo's plain HTML page with `requests`, so search still works if the
package is missing or breaks.
"""
import html
import re

import requests

try:
    from ddgs import DDGS
except ImportError:  # older package name, or not installed
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

HTML_URL = "https://html.duckduckgo.com/html/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_TITLE = re.compile(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', re.S)
_SNIPPET = re.compile(r'<(?:a|div)[^>]*class="result__snippet"[^>]*>(.*?)</(?:a|div)>', re.S)


def _clean(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _search_ddgs(query):
    results = DDGS().text(query, max_results=5) or []
    return [(r.get("title", ""), r.get("body", "")) for r in results]


def _search_html(query):
    r = requests.post(HTML_URL, data={"q": query}, headers=HEADERS, timeout=10)
    r.raise_for_status()
    titles = [_clean(t) for t in _TITLE.findall(r.text)]
    snippets = [_clean(s) for s in _SNIPPET.findall(r.text)]
    return list(zip(titles, snippets))[:5]


def web_search(a):
    query = (a.get("query") or "").strip()
    if not query:
        return "No search query given."
    results, errors = [], []
    for name, fn in (("ddgs", _search_ddgs if DDGS else None), ("html", _search_html)):
        if fn is None:
            continue
        try:
            results = fn(query)
            if results:
                break
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"[search] {name} failed: {e}")
    if not results:
        return "No results found." + (f" Errors: {'; '.join(errors)}" if errors else "")
    return "\n".join(f"- {t}: {b}" for t, b in results)


SKILLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for current or factual information you don't know: news, scores, "
            "opening hours, recent events, facts about people or places. For share prices use "
            "stock_price instead. Summarise the answer briefly for speech; don't read out links."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "run": web_search,
    },
]
