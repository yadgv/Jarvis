"""Remember things without being asked: after each conversation turn, a quick
background call picks out lasting facts about him ("his sister is Mona",
"he works Saturdays") and saves them to memory/facts.json.

Adapted from OpenJarvis's memory/extractor.py (github.com/open-jarvis/OpenJarvis,
Apache License 2.0): same prompt idea, JSON-array answer, forgiving parser,
and it never raises. Turn off with AUTO_MEMORY = False in config.py."""
import json
import re
import threading

import config

MAX_FACTS_PER_TURN = 3
MAX_FACT_CHARS = 200
MIN_WORDS = 5  # "what time is it" style turns are skipped
SYSTEM = (
    "You extract durable, long-term facts about the user from a single conversation exchange with "
    "his voice assistant. A good fact is stable over time and useful in future conversations: "
    "preferences, identity, people in his life, goals, ongoing projects, routines or constraints. "
    "Ignore one-off requests, questions, small talk, anything the assistant said about itself, and "
    "anything already in the known facts. Write each fact in the third person, e.g. \"His sister is "
    "called Mona\".\n\nRespond with ONLY a JSON array of short fact strings (each under 200 characters). "
    "If there is nothing worth remembering, respond with []."
)


def parse(content: str) -> list:
    """Model output -> clean, deduped, capped list of facts (forgiving, like OpenJarvis)."""
    if not content or not content.strip():
        return []
    raw = []
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                raw = [str(x) for x in parsed]
        except ValueError:
            pass
    if not raw and not match:
        raw = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line) for line in content.splitlines() if line.strip()]
    facts, seen = [], set()
    for item in raw:
        fact = item.strip().strip("\"'").strip()[:MAX_FACT_CHARS]
        if not fact or fact.lower() in ("[]", "none", "n/a", "null") or fact.lower() in seen:
            continue
        seen.add(fact.lower())
        facts.append(fact)
        if len(facts) >= MAX_FACTS_PER_TURN:
            break
    return facts


def extract(user_text: str, reply: str, known: list) -> list:
    """Facts worth keeping from one exchange. Never raises."""
    try:
        from brain import llm
        known_text = "\n".join(f"- {f}" for f in known[-60:]) or "(none)"
        text = llm.complete(SYSTEM, f"Known facts:\n{known_text}\n\nExchange:\nUser: {user_text}\n"
                                    f"Assistant: {reply}", max_tokens=300, small=True)
        return parse(text)
    except Exception as e:
        print(f"[memory] auto-extract skipped ({type(e).__name__})")
        return []


# Only turns where he says something about himself can hold a new fact about him
# ("my sister is...", "I work Saturdays"); "show me how to wire a servo" can't.
_PERSONAL = re.compile(r"\b(my|mine|i'm|im|i am|i've|i have|i had|i like|i love|i hate|i prefer|i work|i live|"
                       r"i study|i go|i usually|i always|i never|i need|i want|call me|we're|our)\b", re.I)


def grounded(fact: str, user_text: str) -> bool:
    """The fact must come from what he said this turn, not from the known facts."""
    said = {w[:5] for w in re.findall(r"[a-z0-9]{4,}", user_text.lower())}   # rough stems: work/works
    return any(w[:5] in said for w in re.findall(r"[a-z0-9]{4,}", fact.lower())
               if w not in ("user", "prefers", "likes", "wants"))


def worth_checking(user_text: str, tools_used: list) -> bool:
    if not getattr(config, "AUTO_MEMORY", True):
        return False
    if user_text.lstrip().startswith("["):   # a system note (a finished background job), not him
        return False
    if len(user_text.split()) < MIN_WORDS or not _PERSONAL.search(user_text):
        return False
    # He asked to remember/forget explicitly: the tool already handled it.
    return not any(t.startswith(("remember", "forget")) for t in tools_used)


def run_in_background(user_text: str, reply: str, tools_used: list):
    if not worth_checking(user_text, tools_used):
        return

    def work():
        from brain import memory
        for fact in extract(user_text, reply, memory.load_facts()):
            if not grounded(fact, user_text):
                continue
            result = memory.add_fact(fact)
            print(f"[memory] auto-saved: {fact} ({result})")
    threading.Thread(target=work, daemon=True, name="auto-memory").start()
