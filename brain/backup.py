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


def _post(messages, exclude=(), target=None):
    """target: {"url", "model", "headers"} for another OpenAI-style server
    (the local Ollama model); tools are left out there."""
    if target:
        body = {"model": target["model"], "messages": messages, "max_tokens": 400, "stream": True}
        url, headers, who = target["url"], target.get("headers") or {}, "Local model"
    else:
        models = list(config.OPENROUTER_MODELS)
        body = {
            "model": models[0],
            "messages": messages,
            "tools": skills.openai_tools(exclude),
            "max_tokens": 1500,
            "stream": True,
        }
        if len(models) > 1:
            # OpenRouter tries these in order if the first one is busy or gone.
            body["models"] = models
        url, who = URL, "OpenRouter"
        headers = {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "X-Title": "Jarvis"}
    r = requests.post(url, headers=headers, json=body, stream=True, timeout=(5 if target else 10, 60))
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text)
        except ValueError:
            detail = r.text
        raise RuntimeError(f"{who} error {r.status_code}: {str(detail)[:200]}")
    return r


def _events(response):
    """The JSON chunks of a server-sent-events stream."""
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue  # blank lines and ": OPENROUTER PROCESSING" keep-alives
        data = line[5:].strip()
        if data == "[DONE]":
            return
        chunk = json.loads(data)
        if "error" in chunk:
            raise RuntimeError(f"OpenRouter error: {chunk['error'].get('message', chunk['error'])}")
        yield chunk


def stream_round(messages, exclude=(), target=None):
    """One model call. Yields ("text", piece) while it streams, then
    ("done", (text, tool_calls, model_used)). tool_calls are OpenAI-format dicts."""
    response = _post(messages, exclude, target)
    text, calls, model = "", {}, None
    for chunk in _events(response):
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
