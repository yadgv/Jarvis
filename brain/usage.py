"""Counts the tokens Jarvis sends to the AI models, so savings can be measured.

Free models are counted by size (about 4 characters a token: close enough to
compare one day with another); Claude by the real numbers it sends back.
Totals per day and per brain are kept in memory/token_use.json, and each call
prints a line like "[tokens] Groq openai/gpt-oss-120b ~1,850 in, ~40 out (today ~52k)".
"Saved" counts requests answered with no model at all (a direct command or a
cached answer), with a rough guess of what each would have cost."""
import json
import os
import threading
from datetime import date

import config

_lock = threading.Lock()
# A chat turn on a free model: prompt + trimmed tools + a few turns of history.
SAVED_GUESS = 2500


def _path():
    return os.path.join(config.MEMORY_DIR, "token_use.json")


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    try:
        os.makedirs(config.MEMORY_DIR, exist_ok=True)
        days = sorted(data)[-30:]                 # a month is plenty
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({d: data[d] for d in days}, f, indent=1)
        os.replace(tmp, _path())
    except OSError:
        pass


def estimate(chars: int) -> int:
    return max(0, int(chars) // 4)


def add(who: str, tokens_in: int, tokens_out: int, exact: bool = False):
    """Record one model call. Never raises."""
    try:
        with _lock:
            data = _load()
            day = data.setdefault(date.today().isoformat(), {"in": 0, "out": 0, "calls": 0, "saved": 0, "by": {}})
            day["in"] += tokens_in
            day["out"] += tokens_out
            day["calls"] += 1
            name = (who or "model").split(" ")[0]
            by = day.setdefault("by", {}).setdefault(name, [0, 0])
            by[0] += tokens_in
            by[1] += tokens_out
            _save(data)
            total = day["in"] + day["out"]
        mark = "" if exact else "~"
        print(f"[tokens] {who} {mark}{tokens_in:,} in, {mark}{tokens_out:,} out (today ~{total / 1000:.0f}k)")
    except Exception:
        pass


def saved(why: str):
    """A request answered with no model at all."""
    try:
        with _lock:
            data = _load()
            day = data.setdefault(date.today().isoformat(), {"in": 0, "out": 0, "calls": 0, "saved": 0, "by": {}})
            day["saved"] = day.get("saved", 0) + 1
            _save(data)
        print(f"[tokens] no model needed ({why})")
    except Exception:
        pass


def today() -> dict:
    return _load().get(date.today().isoformat(), {})


def summary() -> str:
    """One line for the log at startup: yesterday's and today's use."""
    data = _load()
    out = []
    for d in sorted(data)[-2:]:
        x = data[d]
        out.append(f"{d}: ~{(x.get('in', 0) + x.get('out', 0)) / 1000:.0f}k tokens in {x.get('calls', 0)} calls, "
                   f"{x.get('saved', 0)} answered with no model")
    return "; ".join(out)
