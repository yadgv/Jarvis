"""Which brain answers, cheapest first (config.BRAIN_ORDER).

  groq        Groq's free API (console.groq.com): fast open models with tool use.
              Each model has its own free limits, so when one is rate-limited
              the next in GROQ_MODELS takes over.
  openrouter  OpenRouter's free models (50 requests a day).
  claude      Claude, paid: the last resort. Screen control and looking at
              the screen always use Claude.

A brain that fails before saying anything is rested for a while and the next
one answers instead, so a busy free model never leaves him without a reply."""
import re
import time

import config
from brain import backup

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_resting = {}  # name or model -> time.monotonic() when it may be tried again


def resting(key) -> bool:
    return time.monotonic() < _resting.get(key, 0)


def rest(key, e: Exception):
    """Rest a model/provider after an error, for as long as the error suggests."""
    status = getattr(e, "status", None) or getattr(e, "status_code", None)
    text = str(e).lower()
    wait = getattr(e, "retry_after", None)
    if wait is None:
        m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", text)
        if m:
            wait = int(m.group(1) or 0) * 60 + float(m.group(2))
    if status in (401, 403):
        seconds = 3600                       # bad key: don't keep hammering it
    elif status == 404 or "does not exist" in text or "decommissioned" in text:
        seconds = 24 * 3600                  # the model is gone (retired): skip it for the day
    elif status == 413 or "too large" in text or "context" in text and "length" in text:
        seconds = 0                          # this request was too big; the next may fit
    elif status == 429 or "rate limit" in text:
        seconds = min(3600, (wait or 60) + 1)
        if "per day" in text or "tokens per day" in text or "requests per day" in text:
            seconds = 3600
    else:
        seconds = 60
    if seconds:
        _resting[key] = time.monotonic() + seconds
    print(f"[brain] {key} failed ({str(e)[:140]}); "
          + (f"resting it {seconds:.0f}s" if seconds else "trying the next one"))


def groq_available() -> bool:
    return bool(getattr(config, "GROQ_API_KEY", None))


def groq_targets(small=False, models=None):
    """Groq models to try in order, skipping rested ones. models: try these first."""
    models = (list(models or []) + list(getattr(config, "GROQ_SMALL_MODELS", []) if small else [])
              + list(config.GROQ_MODELS))
    seen, out = set(), []
    for m in models:
        if m in seen or resting(m):
            continue
        seen.add(m)
        extra = {"reasoning_effort": "low"} if m.startswith("openai/gpt-oss") else {}
        if m.startswith("qwen/"):
            extra = {"reasoning_format": "hidden"}  # its thinking was being spoken aloud
        out.append({"url": GROQ_URL, "model": m, "who": f"Groq {m}", "tools": True, "short_tools": True,
                    "lean": m in getattr(config, "GROQ_LEAN_MODELS", ()),
                    "max_tokens": 1024, "extra": extra,
                    "headers": {"Authorization": f"Bearer {config.GROQ_API_KEY}"}})
    return out


def order():
    """The brains to try this turn, in order."""
    names = [n.lower() for n in getattr(config, "BRAIN_ORDER", ["groq", "openrouter", "claude"])]
    out = []
    for n in names:
        if n == "groq" and groq_available():
            out.append(n)
        elif n == "openrouter" and backup.available() and not resting("openrouter"):
            out.append(n)
        elif n == "claude" and config.ANTHROPIC_API_KEY:
            out.append(n)
    return out
