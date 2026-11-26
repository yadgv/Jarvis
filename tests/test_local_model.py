"""Optional local model (Ollama) for easy questions, with Claude for the rest."""
import pytest

import config
from brain import local_llm
from tests.test_brain import end, llm, use_plan  # noqa: F401


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_MODEL", "llama3.2:3b", raising=False)
    monkeypatch.setattr(local_llm, "_off_until", 0.0)


def fake_local(monkeypatch, llm, pieces=None, error=None):
    calls = []

    def stream_round(messages, exclude=(), target=None):
        calls.append(target)
        assert target and target["model"] == "llama3.2:3b"
        if error:
            raise error
        for p in pieces:
            yield "text", p
        yield "done", ("".join(pieces), [], target["model"])
    monkeypatch.setattr(llm.backup, "stream_round", stream_round)
    return calls


def test_easy_or_not():
    assert local_llm.is_easy("how many ounces are in a pound")
    assert local_llm.is_easy("tell me a joke")
    assert not local_llm.is_easy("what's the weather tomorrow")
    assert not local_llm.is_easy("play some music")
    assert not local_llm.is_easy("explain why the sky is blue")
    assert not local_llm.is_easy("what's on my calendar")
    assert not local_llm.is_easy(" ".join(["word"] * 30))


def test_off_by_default(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_MODEL", "", raising=False)
    assert not local_llm.should_use("tell me a joke")


def test_easy_question_answered_locally(llm, local, monkeypatch):
    fake_local(monkeypatch, llm, ["Sixteen ounces, ", "sir. Quite heavy."])
    use_plan(llm, monkeypatch, lambda m: pytest.fail("Claude was asked"))
    assert list(llm.think_stream("how many ounces in a pound")) == ["Sixteen ounces, sir.", "Quite heavy."]
    assert llm._history[-1]["content"] == "Sixteen ounces, sir. Quite heavy."


def test_handoff_goes_to_claude(llm, local, monkeypatch):
    fake_local(monkeypatch, llm, ["[cla", "ude]"])
    use_plan(llm, monkeypatch, lambda m: end(["Claude here, sir."]))
    assert list(llm.think_stream("who won the cup in 1987")) == ["Claude here, sir."]


def test_ollama_down_uses_claude_and_waits(llm, local, monkeypatch):
    calls = fake_local(monkeypatch, llm, error=ConnectionError("refused"))
    use_plan(llm, monkeypatch, lambda m: end(["Claude here, sir."]))
    assert list(llm.think_stream("tell me a joke")) == ["Claude here, sir."]
    assert list(llm.think_stream("tell me a joke")) == ["Claude here, sir."]
    assert len(calls) == 1  # not retried straight away


def test_hard_question_skips_local(llm, local, monkeypatch):
    calls = fake_local(monkeypatch, llm, ["nope"])
    use_plan(llm, monkeypatch, lambda m: end(["It's sunny."]))
    assert list(llm.think_stream("what's the weather")) == ["It's sunny."]
    assert calls == []
