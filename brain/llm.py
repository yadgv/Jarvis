"""The brain. Keeps short-term conversation memory. Tools get added here in Phase 2."""
import anthropic

import config

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
_history = []  # always whole user/assistant pairs, oldest first


def think(user_text: str) -> str:
    # Trim in whole pairs *before* adding the new turn, so the history
    # always starts with a user message.
    keep = max(0, (config.MAX_HISTORY_TURNS - 1) * 2)
    if len(_history) > keep:
        del _history[: len(_history) - keep]

    _history.append({"role": "user", "content": user_text})
    try:
        response = _client.messages.create(
            model=config.LLM_MODEL,
            max_tokens=300,
            system=config.SYSTEM_PROMPT,
            messages=_history,
        )
    except Exception:
        _history.pop()  # don't leave an unanswered user turn behind
        raise

    reply = "".join(b.text for b in response.content if b.type == "text").strip()
    if not reply:
        _history.pop()
        return ""
    _history.append({"role": "assistant", "content": reply})
    return reply


def reset():
    _history.clear()
