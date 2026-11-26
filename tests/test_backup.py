"""The free OpenRouter backup takes over when Claude can't answer."""
import json
from types import SimpleNamespace as NS

import pytest

import config
from brain import backup


class CreditError(Exception):
    status_code = 400

    def __init__(self):
        super().__init__("Your credit balance is too low to access the Anthropic API.")


class FakeResponse:
    status_code = 200

    def __init__(self, chunks):
        self.lines = [f"data: {json.dumps(c)}" for c in chunks] + ["", "data: [DONE]"]

    def iter_lines(self, decode_unicode=True):
        return iter([": OPENROUTER PROCESSING"] + self.lines)


def text_chunks(*pieces):
    return [{"model": "free-model", "choices": [{"delta": {"content": p}}]} for p in pieces]


def tool_chunks(name, args):
    a = json.dumps(args)
    return [
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1",
                                                "function": {"name": name, "arguments": a[:5]}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": a[5:]}}]}}]},
    ]


@pytest.fixture
def llm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    # These tests cover the Claude-first order (still available in config.BRAIN_ORDER).
    monkeypatch.setattr(config, "BRAIN_ORDER", ["claude", "openrouter"])
    from brain import providers
    monkeypatch.setattr(providers, "_resting", {})
    from brain import llm
    llm._history.clear()
    monkeypatch.setattr(llm, "_claude_off_until", 0.0)
    return llm


def broken_claude(llm, monkeypatch, calls):
    def stream(**kw):
        calls.append(kw)
        raise CreditError()
    monkeypatch.setattr(llm, "_client", NS(messages=NS(stream=stream)))


def fake_openrouter(monkeypatch, *responses):
    sent = []
    queue = list(responses)

    def post(url, headers=None, json=None, **k):
        sent.append(json)
        assert headers["Authorization"] == "Bearer sk-or-test"
        return FakeResponse(queue.pop(0))
    monkeypatch.setattr(backup.requests, "post", post)
    return sent


def test_credit_error_switches_to_backup_and_stays(llm, monkeypatch):
    claude_calls = []
    broken_claude(llm, monkeypatch, claude_calls)
    sent = fake_openrouter(monkeypatch, text_chunks("Hello", " sir. All", " good."),
                           text_chunks("Still here."))
    assert list(llm.think_stream("hi")) == ["Hello sir.", "All good."]
    assert sent[0]["messages"][0]["role"] == "system"
    assert sent[0]["model"] == config.OPENROUTER_MODELS[0]
    assert sent[0]["models"] == config.OPENROUTER_MODELS
    assert sent[0]["tools"] and sent[0]["tools"][0]["type"] == "function"
    # Next turn goes straight to the backup, with the last turn in its history.
    assert list(llm.think_stream("again")) == ["Still here."]
    assert len(claude_calls) == 1
    assert [m["role"] for m in sent[1]["messages"]] == ["system", "user", "assistant", "user"]


def test_backup_runs_tools(llm, monkeypatch):
    broken_claude(llm, monkeypatch, [])
    ran = []
    monkeypatch.setattr(llm.skills, "run", lambda name, args: ran.append((name, args)) or "Set.")
    sent = fake_openrouter(monkeypatch, tool_chunks("set_timer", {"minutes": 5}),
                           text_chunks("Timer set, sir."))
    assert list(llm.think_stream("5 minute timer")) == ["Timer set, sir."]
    assert ran == [("set_timer", {"minutes": 5})]
    follow_up = sent[1]["messages"]
    assert follow_up[-2]["tool_calls"][0]["function"]["name"] == "set_timer"
    assert follow_up[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "Set."}
    assert "set_timer" in llm._history[-1]["content"]


def test_other_errors_are_not_hidden(llm, monkeypatch):
    def stream(**kw):
        raise ValueError("bug in our code")
    monkeypatch.setattr(llm, "_client", NS(messages=NS(stream=stream)))
    fake_openrouter(monkeypatch)
    with pytest.raises(ValueError):
        list(llm.think_stream("hi"))


def test_no_backup_key_keeps_claude_error(llm, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    broken_claude(llm, monkeypatch, [])
    with pytest.raises(CreditError):
        list(llm.think_stream("hi"))


def test_openrouter_error_is_reported(llm, monkeypatch):
    broken_claude(llm, monkeypatch, [])

    class Bad:
        status_code = 429
        text = "slow down"

        def json(self):
            return {"error": {"message": "Rate limit exceeded: free-models-per-day"}}
    monkeypatch.setattr(backup.requests, "post", lambda *a, **k: Bad())
    with pytest.raises(RuntimeError, match="free-models-per-day"):
        list(llm.think_stream("hi"))


def test_classifier():
    assert backup.claude_unavailable(CreditError())
    assert backup.claude_unavailable(type("RateLimitError", (Exception,), {})("x"))
    assert not backup.claude_unavailable(ValueError("bad value"))


def test_screen_says_it_needs_claude(monkeypatch):
    from skills import screen
    monkeypatch.setattr(screen, "ImageGrab", object())
    monkeypatch.setattr(screen, "capture", lambda: "img")

    def ask(*a):
        raise CreditError()
    monkeypatch.setattr(screen, "_ask", ask)
    assert screen.look_at_screen({}) == backup.NEEDS_CLAUDE
