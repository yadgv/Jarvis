"""Web search through DuckDuckGo (free, no API key) via the `ddgs` package."""
try:
    from ddgs import DDGS
except ImportError:  # older package name
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


def web_search(a):
    query = (a.get("query") or "").strip()
    if not query:
        return "No search query given."
    if DDGS is None:
        return "Web search isn't installed. Run: pip install ddgs"
    results = DDGS().text(query, max_results=5)
    if not results:
        return "No results found."
    return "\n".join(
        f"- {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})" for r in results
    )


SKILLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for current or factual information you don't know: news, scores, "
            "prices, opening hours, recent events, facts about people or places. "
            "Summarise the answer briefly for speech; don't read out links."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "run": web_search,
    },
]
