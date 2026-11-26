"""Claude is the last resort: Groq's free models answer first, then OpenRouter, then Claude."""
import json
from types import SimpleNamespace as NS

import pytest

import config
import skills
from brain import backup, providers


class Resp:
    def __init__(self, chunks=(), status=200, error=None, headers=None):
        self.status_code, self.error, self.headers = status, error, headers or {}
        self.lines = [f"data: {json.dumps(c)}" for c in chunks] + ["data: [DONE]"]

    def iter_lines(self, decode_unicode=True):
        return iter(self.lines)

    def json(self):
        return {"error": {"message": self.error}}

    text = "error"


def says(*pieces):
    return Resp([{"model": "m", "choices": [{"delta": {"content": p}}]} for p in pieces])


def calls_tool(name, args):
    return Resp([{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {
        "name": name, "arguments": json.dumps(args)}}]}}]}])


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr(config, "BRAIN_ORDER", ["groq", "openrouter", "claude"])
    monkeypatch.setattr(config, "GROQ_MODELS", ["groq-big", "groq-other"])
    monkeypatch.setattr(providers, "_resting", {})
    from brain import llm
    llm._history.clear()
    monkeypatch.setattr(llm, "_claude_off_until", 0.0)
    claude = []

    def stream(**kw):
        claude.append(kw)
        raise AssertionError("Claude shouldn't be used")
    monkeypatch.setattr(llm, "_client", NS(messages=NS(stream=stream)))
    sent, replies = [], []

    def post(url, headers=None, json=None, **k):
        sent.append((url, json))
        return replies.pop(0)
    monkeypatch.setattr(backup.requests, "post", post)
    return NS(llm=llm, sent=sent, replies=replies, claude=claude)


def test_groq_answers_first_with_few_tools(brain):
    brain.replies.append(says("It's sunny, sir."))
    assert list(brain.llm.think_stream("what's the weather like?")) == ["It's sunny, sir."]
    url, body = brain.sent[0]
    assert "groq.com" in url and body["model"] == "groq-big" and not brain.claude
    names = {t["function"]["name"] for t in body["tools"]}
    assert "get_weather" in names and len(names) < len(skills.SKILLS) // 2
    assert all(len(t["function"]["description"]) <= 160 for t in body["tools"])


def test_rate_limited_model_rests_and_next_takes_over(brain):
    brain.replies += [Resp(status=429, error="Rate limit reached. Please try again in 7.5s"), says("Hello.")]
    assert list(brain.llm.think_stream("hi")) == ["Hello."]
    assert [b["model"] for _, b in brain.sent] == ["groq-big", "groq-other"]
    assert providers.resting("groq-big") and not providers.resting("groq-other")
    brain.replies.append(says("Again."))
    list(brain.llm.think_stream("hi again"))
    assert brain.sent[-1][1]["model"] == "groq-other"  # the rested one is skipped


def test_falls_back_to_openrouter_then_claude(brain, monkeypatch):
    brain.replies += [Resp(status=429, error="limit"), Resp(status=429, error="limit"), says("From OpenRouter.")]
    assert list(brain.llm.think_stream("hi")) == ["From OpenRouter."]
    assert "openrouter" in brain.sent[-1][0]
    # Everything free is down: Claude answers.
    brain.replies.append(Resp(status=429, error="free-models-per-day"))

    class Final:
        stop_reason, content = "end_turn", []

    class Stream:
        text_stream = iter(["Claude here."])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get_final_message(self):
            return Final()
    monkeypatch.setattr(brain.llm, "_client", NS(messages=NS(stream=lambda **kw: Stream())))
    assert list(brain.llm.think_stream("hi again")) == ["Claude here."]


def test_tools_already_run_are_not_repeated(brain, monkeypatch):
    ran = []
    monkeypatch.setattr(brain.llm.skills, "run", lambda n, a: ran.append(n) or "Timer set.")
    brain.replies += [calls_tool("set_timer", {"minutes": 5}), Resp(status=429, error="limit"),
                      says("Done, sir.")]
    assert list(brain.llm.think_stream("set a 5 minute timer")) == ["Done, sir."]
    assert ran == ["set_timer"]
    assert "Already done this turn" in brain.sent[-1][1]["messages"][-1]["content"]


def test_complete_uses_free_models(brain):
    brain.replies.append(says("- likes tea"))
    assert brain.llm.complete("sys", "text") == "- likes tea"
    assert "tools" not in brain.sent[0][1]


def test_no_brain_at_all(brain, monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", None)
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        list(brain.llm.think_stream("hi"))


def test_pick_tools():
    keep = skills.pick_tools("remind me to call mum on Friday")
    assert "set_reminder" in keep and "remember" in keep and len(keep) < 15
    assert "dark_mode" in skills.pick_tools("turn on dark mode")


def test_yes_keeps_last_turns_tool(brain):
    brain.llm._history += [{"role": "user", "content": "reply to Sam"},
                           {"role": "assistant", "content": "Shall I send it? [tools used: reply_email -> DRAFT]"}]
    brain.replies.append(says("Sent."))
    list(brain.llm.think_stream("yes"))
    names = {t["function"]["name"] for t in brain.sent[0][1]["tools"]}
    assert "reply_email" in names
