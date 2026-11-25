"""The brain: Claude, conversation memory, and tools (see skills/)."""
import re
from datetime import datetime

import anthropic

import config
from brain import memory
import skills

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Whole user/assistant text pairs, oldest first. Loaded from disk so the
# conversation survives a restart.
_history = memory.load_history()
if _history:
    print(f"[memory] picked up the last conversation ({len(_history) // 2} turns)")

# End of a sentence: . ! or ? (plus closing quotes/brackets) followed by a space.
# Needing the space keeps numbers like "3.5" together.
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*\s+")

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


def think_stream(user_text: str):
    """Yields the reply one sentence at a time while Claude is still writing,
    so Jarvis can start speaking the first sentence straight away.
    If Claude uses a tool (remember/forget), runs it and carries on."""
    _trim()
    # Tool calls live only in this turn's working copy; the saved history
    # keeps just what was said, so it stays simple user/assistant pairs.
    messages = _history + [{"role": "user", "content": user_text}]
    # Build the system prompt once per turn: Claude's thinking blocks are tied
    # to it, so if the clock ticked over to a new minute between tool rounds the
    # API rejected the second round ("Invalid signature in thinking block").
    system = _system_prompt()
    said, tools_used = [], []
    stop_reason = None
    try:
        for _ in range(MAX_TOOL_ROUNDS + 1):
            buf = ""
            with _client.messages.stream(
                model=config.LLM_MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": LLM_EFFORT},
                system=system,
                messages=messages,
                tools=skills.anthropic_tools(),
            ) as stream:
                for delta in stream.text_stream:
                    buf += delta
                    while (m := _SENTENCE_END.search(buf)):
                        sentence = buf[: m.end()].strip()
                        buf = buf[m.end():]
                        if sentence:
                            said.append(sentence)
                            yield sentence
                final = stream.get_final_message()
            if buf.strip():
                said.append(buf.strip())
                yield buf.strip()

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
    finally:
        reply = " ".join(said)
        if reply:
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
