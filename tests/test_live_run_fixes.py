"""Fixes from his first live test-bench run (Nov 26)."""
import json

import config
from brain import backup, llm, providers


class Resp:
    status_code = 200
    encoding = None

    def __init__(self, chunks):
        self.lines = [f"data: {json.dumps(c)}" for c in chunks] + ["data: [DONE]"]

    def iter_lines(self, decode_unicode=True):
        return iter(self.lines)


def test_gemini_thought_signature_goes_back_with_the_call(monkeypatch):
    sig = {"google": {"thought_signature": "abc"}}
    chunk = {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "extra_content": sig,
                                                    "function": {"name": "media", "arguments": "{}"}}]}}]}
    monkeypatch.setattr(backup, "_post", lambda *a, **k: Resp([chunk]))
    done = [v for k, v in backup.stream_round([], (), {}) if k == "done"][0]
    assert done[1][0]["extra_content"] == sig


def _only_groq(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "g")
    monkeypatch.setattr(config, "GROQ_MODELS", ["g1"])
    for k in ("CEREBRAS_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "GITHUB_MODELS_TOKEN",
              "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setattr(config, k, None, raising=False)
    providers._resting.clear()


def test_model_breaking_after_the_tool_still_reports_the_result(monkeypatch):
    import skills
    _only_groq(monkeypatch)
    rounds = []

    def fake_round(messages, exclude, target):
        rounds.append(1)
        if len(rounds) == 1:
            yield "done", ("", [{"id": "c1", "type": "function",
                                 "function": {"name": "set_timer", "arguments": "{\"minutes\": 10}"}}], "g1")
            return
        raise backup.ProviderError("no answer in the reply (OK)")
        yield
    ran = []
    monkeypatch.setattr(backup, "stream_round", fake_round)
    monkeypatch.setattr(skills, "run", lambda n, a: ran.append(n) or "Timer set for 10 minutes.")
    out = list(llm._chain("Set a timer for 10 minutes", "sys", [], []))
    assert ran == ["set_timer"] and out == ["Timer set for 10 minutes."]
    assert not providers._resting          # nothing rested: the turn worked
    providers._resting.clear()


def test_bracketed_notes_are_never_spoken():
    assert not llm._speakable("[This reply was produced without calling a tool.")
    assert not llm._speakable("[tools used: set_timer -> done]")
    assert llm._speakable("You're on CBC News, reading about a data breach.")


def test_bench_waits_for_a_resting_model(monkeypatch):
    import time
    import run_tests
    providers._resting.clear()
    assert run_tests.rest_wait(5) == 20
    providers._resting["groq"] = time.monotonic() + 45
    assert 45 <= run_tests.rest_wait(5) <= 47
    providers._resting["x"] = time.monotonic() + 9999
    providers._resting["groq"] = time.monotonic() + 9999
    assert run_tests.rest_wait(5) == 120
    providers._resting.clear()
