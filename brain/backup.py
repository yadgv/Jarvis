"""Backup brain: a free model on OpenRouter, used when Claude can't answer
(credits ran out, key problem, rate limit). OpenRouter speaks the OpenAI chat
format, so this talks to it with plain `requests`.

Free models allow 20 requests a minute and 50 a day (1000 a day once you've
bought $10 of OpenRouter credits at any point). One spoken reply that uses a
tool counts as two requests.
"""
import json

import requests

import config
import skills

URL = "https://openrouter.ai/api/v1/chat/completions"
# Seconds to wait for a server to answer the phone. A working connection takes
# well under a second; long waits only happen when the wifi is down.
CONNECT_TIMEOUT = 4


# Errors that mean "Claude can't answer right now, but another model could".
_OUT_OF_SERVICE = {"AuthenticationError", "PermissionDeniedError", "RateLimitError",
                   "OverloadedError", "InternalServerError", "ServiceUnavailableError"}
_OUT_OF_SERVICE_TEXT = ("credit balance", "billing", "quota", "insufficient", "authentication",
                        "api key", "api_key", "rate limit", "overloaded")


def claude_unavailable(e: Exception) -> bool:
    if type(e).__name__ in _OUT_OF_SERVICE:
        return True
    if getattr(e, "status_code", None) in (401, 402, 403, 429, 500, 503, 529):
        return True
    text = str(e).lower()
    return any(t in text for t in _OUT_OF_SERVICE_TEXT)


NEEDS_CLAUDE = ("This needs Claude, and Claude isn't available right now (probably out of credits). "
                "Tell the user screen control only works with Claude, so it'll be back once credits are topped up.")


def available() -> bool:
    return bool(config.OPENROUTER_API_KEY)


class ProviderError(RuntimeError):
    """An OpenAI-style server said no; status is the HTTP code (429 = rate limit)."""
    def __init__(self, message, status=None, retry_after=None):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


def openrouter_target():
    models = list(config.OPENROUTER_MODELS)
    # Short tool list and history, like Groq: fewer tokens is faster and leaves free limits for later.
    t = {"url": URL, "model": models[0], "who": "OpenRouter", "tools": True, "short_tools": True, "max_tokens": 1500,
         "timeout": (CONNECT_TIMEOUT, 20),
         "headers": {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "X-Title": "Jarvis"}}
    if len(models) > 1:
        t["extra"] = {"models": models}  # OpenRouter tries these in order if the first one is busy or gone
    return t


def _post(messages, exclude=(), target=None):
    """target: {"url", "model", "headers", "who", "tools", "short_tools", "max_tokens", "extra"}
    for any OpenAI-style server (OpenRouter, Groq, the local Ollama model).
    No target means OpenRouter with all tools."""
    target = target or openrouter_target()
    body = {"model": target["model"], "messages": messages,
            "max_tokens": target.get("max_tokens", 400), "stream": True}
    if target.get("tools"):
        body["tools"] = skills.openai_tools(exclude, short=target.get("short_tools", False))
        if target.get("drop_empty_params"):
            # Gemini refuses an object with no properties: leave such parameters out.
            for t in body["tools"]:
                if not (t["function"].get("parameters") or {}).get("properties"):
                    t["function"].pop("parameters", None)
    body.update(target.get("extra") or {})
    who = target.get("who", "Local model")
    r = requests.post(target["url"], headers=target.get("headers") or {}, json=body, stream=True,
                      timeout=target.get("timeout") or (CONNECT_TIMEOUT, 60))
    if r.status_code != 200:
        detail = error_text(r)
        retry = None
        try:
            retry = float(r.headers.get("retry-after"))
        except (AttributeError, TypeError, ValueError):
            pass
        raise ProviderError(f"{who} error {r.status_code}: {str(detail)[:200]}", r.status_code, retry)
    return r


def _events(response, who="model"):
    """The JSON chunks of a server-sent-events stream."""
    # These streams are UTF-8, but say "text/event-stream" with no charset, so
    # requests would decode them as Latin-1 and "servo's" becomes "servoâs".
    response.encoding = "utf-8"
    seen, other = False, []
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            if line and not line.startswith(":"):
                other.append(line)   # not a stream at all (some servers answer plain JSON)
            continue  # blank lines and ": OPENROUTER PROCESSING" keep-alives
        data = line[5:].strip()
        if data == "[DONE]":
            return
        seen = True
        chunk = json.loads(data)
        for c in (chunk if isinstance(chunk, list) else [chunk]):
            if not isinstance(c, dict):
                continue
            if "error" in c:
                err = c["error"]
                raise ProviderError(f"Model error: {err.get('message', err) if isinstance(err, dict) else err}",
                                    err.get("code") if isinstance(err, dict) else None)
            yield c
    if not seen:
        raw = " ".join(other)[:300]
        try:   # a plain (non-streamed) answer: use it
            whole = json.loads(" ".join(other))
            if isinstance(whole, dict) and whole.get("choices"):
                msg = whole["choices"][0].get("message") or {}
                yield {"model": whole.get("model"), "choices": [{"delta": {
                    "content": msg.get("content") or "",
                    "tool_calls": [dict(tc, index=i) for i, tc in enumerate(msg.get("tool_calls") or [])]}}]}
                return
        except ValueError:
            pass
        kind = (getattr(response, "headers", None) or {}).get("content-type", "?")
        raise ProviderError(f"{who} sent no answer in the reply ({raw or 'empty'}, {kind})", "empty")


def error_text(r) -> str:
    """The message in an error answer, whatever its shape (Gemini sends a list: [{"error": {...}}])."""
    try:
        j = r.json()
    except ValueError:
        return r.text
    if isinstance(j, list) and j:
        j = j[0]
    err = j.get("error") if isinstance(j, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err or j or r.text)


def stream_round(messages, exclude=(), target=None):
    """One model call. Yields ("text", piece) while it streams, then
    ("done", (text, tool_calls, model_used)). tool_calls are OpenAI-format dicts."""
    response = _post(messages, exclude, target)
    text, calls, model = "", {}, None
    for chunk in _events(response, (target or {}).get("who") or "OpenRouter"):
        model = chunk.get("model") or model
        for choice in chunk.get("choices", []):
            delta = choice.get("delta") or {}
            if delta.get("content"):
                text += delta["content"]
                yield "text", delta["content"]
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", len(calls)),
                                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                if tc.get("extra_content"):
                    # Gemini's thought_signature: it must come back with the call, or the
                    # next round fails ("Function call is missing a thought_signature").
                    slot["extra_content"] = tc["extra_content"]
                fn = tc.get("function") or {}
                slot["function"]["name"] += fn.get("name") or ""
                slot["function"]["arguments"] += fn.get("arguments") or ""
    tool_calls = [calls[i] for i in sorted(calls)]
    for i, c in enumerate(tool_calls):
        c["id"] = c["id"] or f"call_{i}"
    yield "done", (text, tool_calls, model)


def parse_args(call) -> dict:
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
        return args if isinstance(args, dict) else {}
    except ValueError:
        return {}
