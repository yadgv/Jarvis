"""Memory that survives restarts.

- history.json: the recent conversation, so Jarvis picks up where you left off.
  It's ignored if it's older than HISTORY_MAX_AGE_HOURS.
- facts.json: lasting facts about you ("my sister is called Mona"), saved
  when you ask Jarvis to remember something and given to him on every request.

Both live in the memory/ folder, which git ignores.
"""
import json
import os
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
def load_facts() -> list:
    facts = _read("facts.json", [])
    return [f for f in facts if isinstance(f, str)] if isinstance(facts, list) else []


def add_fact(fact: str) -> str:
    fact = fact.strip()
    if not fact:
        return "Nothing to remember."
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
