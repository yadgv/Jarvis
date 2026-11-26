"""Memory that survives restarts.

- history.json: the recent conversation, so Jarvis picks up where you left off.
  It's ignored if it's older than HISTORY_MAX_AGE_HOURS.
- facts.json: lasting facts about you ("my sister is called Mona"), saved
  when you ask Jarvis to remember something and given to him on every request.

Both live in the memory/ folder, which git ignores.
"""
import json
import math
import os
import re
import time

import config


def _path(name):
    return os.path.join(config.MEMORY_DIR, name)


def _read(name, default):
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(name, data):
    os.makedirs(config.MEMORY_DIR, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(name))  # never leaves a half-written file


# ---------- conversation history ----------
def load_history() -> list:
    data = _read("history.json", {})
    saved_at = data.get("saved_at", 0)
    if time.time() - saved_at > config.HISTORY_MAX_AGE_HOURS * 3600:
        return []
    messages = data.get("messages", [])
    # Only keep well-formed user/assistant text pairs.
    ok = (
        isinstance(messages, list)
        and len(messages) % 2 == 0
        and all(
            isinstance(m, dict)
            and m.get("role") == ("user" if i % 2 == 0 else "assistant")
            and isinstance(m.get("content"), str)
            for i, m in enumerate(messages)
        )
    )
    return messages if ok else []


def save_history(messages: list):
    try:
        _write("history.json", {"saved_at": time.time(), "messages": messages})
    except OSError as e:
        print(f"[memory] couldn't save conversation ({e})")


# ---------- long-term facts ----------
_META_FACT = re.compile(r"\b(?:wants|asked|asks|told)\b.{0,20}\b(?:assistant|jarvis|you)\b.{0,10}\bto remember\b", re.I)


def is_junk(fact: str) -> bool:
    """Not a fact worth keeping: a lone word ("Tuesday", a misheard sentence) or a
    note about remembering rather than the thing itself."""
    words = re.findall(r"[\w'-]+", fact or "")
    return len(words) < 3 or bool(_META_FACT.search(fact or ""))


def load_facts() -> list:
    facts = _read("facts.json", [])
    return [f for f in facts if isinstance(f, str) and not is_junk(f)] if isinstance(facts, list) else []


def add_fact(fact: str) -> str:
    fact = fact.strip()
    if not fact:
        return "Nothing to remember."
    if is_junk(fact):
        print(f"[memory] not saved (not a clear fact): {fact}")
        return ("Not saved: that isn't a clear fact. Ask him what exactly to remember, as a full sentence "
                "(e.g. 'my exam is on Tuesday').")
    facts = load_facts()
    if fact.lower() in (f.lower() for f in facts):
        return "Already remembered."
    facts.append(fact)
    facts = facts[-config.MAX_FACTS:]
    _write("facts.json", facts)
    print(f"[memory] remembered: {fact}")
    return "Saved."


def remove_facts(about: str) -> str:
    about = about.strip().lower()
    facts = load_facts()
    keep = [f for f in facts if about not in f.lower()] if about else facts
    removed = len(facts) - len(keep)
    if removed:
        _write("facts.json", keep)
        print(f"[memory] forgot {removed} fact(s) about: {about}")
        return f"Removed {removed} fact(s)."
    return "No saved fact matched."


# ---------- picking the facts that matter ----------
# Once there are lots of saved facts, sending them all on every request costs
# tokens and buries the useful ones. Word lists and terms() are from GLaDOS's
# memory_recall.py (github.com/dnhkng/GLaDOS, MIT License, Copyright (c) 2022
# David Ng); the scoring is a simplified version of its rarity-weighted match.
_STOP = set(
    "a an the and or of to in on for with from by is are was were be been being "
    "i me my mine we our you your it its this that these those they them their "
    "what which who when where why how do does did have has had can could would "
    "should will may about at as not no yes please tell say know remember recall "
    "fact facts memory stored saved again also then now any some all much many".split()
)
_ALIASES = {
    word: canonical
    for canonical, words in {
        "gpu": "gpu gpus vram graphics",
        "ram": "ram",
        "prefer": "prefer prefers preferred preference preferences",
        "food": "food foods meal meals dinner lunch supper dish dishes",
        "name": "name names named",
    }.items()
    for word in words.split()
}


def terms(text: str) -> set:
    return {_ALIASES.get(word, word) for word in re.findall(r"[^\W_]+", text.casefold()) if word not in _STOP}


def relevant_facts(facts: list, about: str, limit: int, newest: int = 5) -> list:
    """Up to `limit` facts, in their saved order: the `newest` most recent
    ones (likely still being talked about) plus the best word matches for
    `about`, rare words counting more than common ones."""
    if len(facts) <= limit:
        return facts
    fact_terms = [terms(f) for f in facts]
    df = {}
    for ts in fact_terms:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    query = terms(about)
    scores = [sum(math.log(1 + len(facts) / df[t]) for t in ts & query) for ts in fact_terms]
    keep = set(range(len(facts) - newest, len(facts)))
    for i in sorted(range(len(facts)), key=lambda i: (-scores[i], -i)):
        if len(keep) >= limit:
            break
        if scores[i] > 0:
            keep.add(i)
    return [f for i, f in enumerate(facts) if i in keep]
