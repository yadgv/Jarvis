"""The brain. Keeps short-term conversation memory. Tools get added here in Phase 2."""
import re

import anthropic

import config

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
_history = []  # always whole user/assistant pairs, oldest first

# End of a sentence: . ! or ? (plus closing quotes/brackets) followed by a space.
# Needing the space keeps numbers like "3.5" together.
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*\s+")


def _trim():
    # Trim in whole pairs *before* adding the new turn, so the history
    # always starts with a user message.
    keep = max(0, (config.MAX_HISTORY_TURNS - 1) * 2)
    if len(_history) > keep:
        del _history[: len(_history) - keep]


def think_stream(user_text: str):
    """Yields the reply one sentence at a time while Claude is still writing,
    so Jarvis can start speaking the first sentence straight away."""
    _trim()
    _history.append({"role": "user", "content": user_text})
    said = []
    try:
        buf = ""
        with _client.messages.stream(
            model=config.LLM_MODEL,
            max_tokens=300,
            system=config.SYSTEM_PROMPT,
            messages=_history,
        ) as stream:
            for delta in stream.text_stream:
                buf += delta
                while (m := _SENTENCE_END.search(buf)):
                    sentence = buf[: m.end()].strip()
                    buf = buf[m.end():]
                    if sentence:
                        said.append(sentence)
                        yield sentence
        if buf.strip():
            said.append(buf.strip())
            yield buf.strip()
    finally:
        # Remember what was actually said; if nothing was, drop the
        # unanswered user turn so the history stays in pairs.
        reply = " ".join(said)
        if reply:
            _history.append({"role": "assistant", "content": reply})
        else:
            _history.pop()


def think(user_text: str) -> str:
    """Whole reply at once (handy for testing)."""
    return " ".join(think_stream(user_text))


def reset():
    _history.clear()
