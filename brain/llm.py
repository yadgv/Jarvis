"""The brain: Claude, conversation memory, and tools (see skills/)."""
import re
import time
from datetime import datetime

import anthropic

import config
from brain import backup, memory
import skills

# The SDK's defaults (10 minute timeout, 2 retries) let one stuck request
# freeze Jarvis for up to half an hour; seen twice in jarvis.log on 25 Nov.
# For a stream the timeout is the longest gap between chunks, not the whole reply.
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=30.0, max_retries=1)

# Whole user/assistant text pairs, oldest first. Loaded from disk so the
# conversation survives a restart.
_history = memory.load_history()
if _history:
    print(f"[memory] picked up the last conversation ({len(_history) // 2} turns)")

# End of a sentence: . ! or ? (plus closing quotes/brackets) followed by a space.
# Needing the space keeps numbers like "3.5" together.
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*\s+")
# A comma/semicolon/dash pause; used to start speaking the first reply sooner.
_CLAUSE_END = re.compile(r"(?:[,;:]|\s[-\u2013\u2014])\s+")
FIRST_CLAUSE_WORDS = 5

MAX_TOOL_ROUNDS = 4
# Room for Claude's (hidden) thinking plus a short spoken reply. With 300 the
# thinking alone could use everything up and Jarvis said nothing at all.
MAX_TOKENS = 1500
# Low effort = less thinking = faster replies; fine for voice chat.
LLM_EFFORT = getattr(config, "LLM_EFFORT", "low")
# Saved history keeps only what was said, so without this Claude sees itself
# saying "Apple Music is open" with no tool call and "corrects" itself.
_HISTORY_NOTE = (
    "\nEarlier turns are stored as plain text; any tools you used then are noted "
    "in [square brackets] at the end of your reply. Never read those notes aloud, "
    "and don't apologise for or correct earlier replies unless he says something was wrong."
)


def _system_prompt() -> str:
    """The configured prompt plus the current local date and time, so Jarvis
    can answer "what time is it?", plus everything he's been asked to remember."""
    now = datetime.now().astimezone()
    hour = now.strftime("%I").lstrip("0") or "12"
    stamp = now.strftime(f"%A %d %B %Y, {hour}:%M %p")
    prompt = f"{config.SYSTEM_PROMPT}{_HISTORY_NOTE}\nCurrent local date and time: {stamp} ({now.tzname()})."
    facts = memory.load_facts()
    if facts:
        prompt += "\nThings you know about the user:\n" + "\n".join(f"- {f}" for f in facts)
    return prompt


def _trim():
    # Trim in whole pairs before adding the new turn, so the history
    # always starts with a user message.
    keep = max(0, (config.MAX_HISTORY_TURNS - 1) * 2)
    if len(_history) > keep:
        del _history[: len(_history) - keep]


# When Claude stops working for billing/key/limit reasons, Jarvis uses the
# backup model for this long before trying Claude again.
BACKUP_MINUTES = getattr(config, "BACKUP_MINUTES", 15)
_claude_off_until = 0.0
last_ignored = False  # the last follow-up wasn't meant for Jarvis
def _use_claude() -> bool:
    if not config.ANTHROPIC_API_KEY and backup.available():
        return False
    return time.monotonic() >= _claude_off_until


def _first_break(buf, said):
    """The first thing he says can end at a comma once it's a few words long,
    so his voice starts sooner; later ones wait for the full sentence."""
    m = _SENTENCE_END.search(buf)
    if said or m:
        return m
    for m in _CLAUSE_END.finditer(buf):
        if len(buf[: m.start()].split()) >= FIRST_CLAUSE_WORDS:
            return m
    return None


def _sentences(pieces, said):
    """Turns streamed text pieces into whole sentences as soon as each ends."""
    buf = ""
    for delta in pieces:
        buf += delta
        while (m := _first_break(buf, said)):
            sentence = buf[: m.end()].strip()
            buf = buf[m.end():]
            if sentence:
                said.append(sentence)
                yield sentence
    if buf.strip():
        said.append(buf.strip())
        yield buf.strip()


def _claude_turn(user_text, system, said, tools_used, exclude=()):
    # Tool calls live only in this turn's working copy; the saved history
    # keeps just what was said, so it stays simple user/assistant pairs.
    messages = _history + [{"role": "user", "content": user_text}]
    stop_reason = None
    for _ in range(MAX_TOOL_ROUNDS + 1):
        with _client.messages.stream(
            model=config.LLM_MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": LLM_EFFORT},
            system=system,
            messages=messages,
            tools=skills.anthropic_tools(exclude),
        ) as stream:
            yield from _sentences(stream.text_stream, said)
            final = stream.get_final_message()

        stop_reason = final.stop_reason
        tool_uses = [b for b in final.content if b.type == "tool_use"]
        if final.stop_reason != "tool_use" or not tool_uses:
            break
        messages.append({"role": "assistant", "content": final.content})
        results = []
        for b in tool_uses:
            out = skills.run(b.name, b.input)
            tools_used.append(f"{b.name} -> {str(out)[:80]}")
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        messages.append({"role": "user", "content": results})
    if not said:
        print(f"[brain] Claude finished without saying anything (stop: {stop_reason})")


def _backup_turn(user_text, system, said, tools_used, exclude=()):
    """The same turn on the free OpenRouter model (OpenAI message format)."""
    messages = ([{"role": "system", "content": system}] + list(_history)
                + [{"role": "user", "content": user_text}])
    t0 = time.perf_counter()
    model = None
    for _ in range(MAX_TOOL_ROUNDS + 1):
        result = {}

        def pieces():
            for kind, value in backup.stream_round(messages, exclude):
                if kind == "text":
                    yield value
                else:
                    result["done"] = value
        yield from _sentences(pieces(), said)
        text, tool_calls, model = result["done"]
        if not tool_calls:
            break
        messages.append({"role": "assistant", "content": text or None, "tool_calls": tool_calls})
        for call in tool_calls:
            name = call["function"]["name"]
            out = skills.run(name, backup.parse_args(call))
            tools_used.append(f"{name} -> {str(out)[:80]}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
    print(f"[brain] backup model {model or '?'} answered in {time.perf_counter() - t0:.1f}s")


# Added to what was heard when Jarvis keeps listening after a reply (no wake
# word), so he stays quiet when it's someone else talking in the room.
FOLLOWUP_NOTE = (
    "[Heard without the wake word, a few seconds after your last reply. It may be "
    "someone else in the room, or him talking to someone else. Answer only if it is "
    "clearly meant for you: a question or request to you, or a direct reply to what "
    "you just said. Otherwise answer with exactly [ignore] and nothing else.]\n"
)
IGNORE = "[ignore]"


def think_stream(user_text: str, followup: bool = False, note: str = ""):
    """Yields the reply one sentence at a time while Claude is still writing,
    so Jarvis can start speaking the first sentence straight away.
    If Claude uses a tool (remember/forget), runs it and carries on.
    If Claude is out of credits (or the key or rate limit fails), the free
    backup model on OpenRouter answers instead."""
    global _claude_off_until, last_ignored
    last_ignored = False
    skills.new_turn()
    _trim()
    asked = (FOLLOWUP_NOTE if followup else "") + note + user_text
    # Overheard chatter must never be able to switch him off.
    exclude = ("shut_down",) if followup else ()
    # Build the system prompt once per turn: Claude's thinking blocks are tied
    # to it, so if the clock ticked over to a new minute between tool rounds the
    # API rejected the second round ("Invalid signature in thinking block").
    system = _system_prompt()
    said, tools_used = [], []

    def turn():
        global _claude_off_until
        if not _use_claude():
            yield from _backup_turn(asked, system, said, tools_used, exclude)
            return
        try:
            yield from _claude_turn(asked, system, said, tools_used, exclude)
        except Exception as e:
            # Only switch if nothing was spoken yet, so he never hears a reply twice.
            if said or not backup.available() or not backup.claude_unavailable(e):
                raise
            _claude_off_until = time.monotonic() + BACKUP_MINUTES * 60
            print(f"[brain] Claude unavailable ({type(e).__name__}: {str(e)[:150]}), "
                  f"using the backup model for the next {BACKUP_MINUTES} minutes")
            tools_used.clear()
            yield from _backup_turn(asked, system, said, tools_used, exclude)

    gen = turn()
    try:
        for sentence in gen:
            if followup and len(said) == 1 and sentence.lower().startswith(IGNORE[:-1]):
                last_ignored = True
                print(f"[brain] ignored (not meant for Jarvis): {user_text}")
                break
            yield sentence
    finally:
        gen.close()
        reply = " ".join(said)
        if reply and not last_ignored:
            if tools_used:
                reply += " [tools used: " + "; ".join(tools_used) + "]"
            _history.append({"role": "user", "content": user_text})
            _history.append({"role": "assistant", "content": reply})
            memory.save_history(_history)


def think(user_text: str) -> str:
    """Whole reply at once (handy for testing)."""
    return " ".join(think_stream(user_text))


def reset():
    """Start a fresh conversation (saved facts are kept)."""
    _history.clear()
    memory.save_history(_history)
