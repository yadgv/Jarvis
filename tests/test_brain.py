from types import SimpleNamespace as NS

import pytest

import config


class FakeStream:
    """Mimics anthropic's messages.stream() context manager."""

    def __init__(self, plan, kwargs):
        self.plan, self.kwargs = plan, kwargs

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    @property
    def text_stream(self):
        msgs = self.kwargs["messages"]
        assert msgs[0]["role"] == "user"
        for a, b in zip(msgs, msgs[1:]):
            assert a["role"] != b["role"]
        self.texts, self.final = self.plan(msgs)
        yield from self.texts

    def get_final_message(self):
        return self.final


@pytest.fixture
def llm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    from brain import llm
    llm._history.clear()
    return llm


def use_plan(llm, monkeypatch, plan):
    client = NS(messages=NS(stream=lambda **kw: FakeStream(plan, kw)))
    monkeypatch.setattr(llm, "_client", client)


def end(texts):
    return texts, NS(stop_reason="end_turn", content=[])


def test_sentences_split_while_streaming(llm, monkeypatch):
    use_plan(llm, monkeypatch, lambda m: end(["Good eve", "ning, sir. It is 3.5 deg", "rees! Tea?"]))
    assert list(llm.think_stream("hi")) == ["Good evening, sir.", "It is 3.5 degrees!", "Tea?"]


def test_history_stays_in_pairs_and_is_trimmed(llm, monkeypatch):
    def plan(m):
        if m[-1]["content"] == "fail":
            raise RuntimeError("network")
        return end(["ok."])
    use_plan(llm, monkeypatch, plan)
    for i in range(30):
        try:
            llm.think("fail" if i % 7 == 3 else f"q{i}")
        except RuntimeError:
            pass
    assert len(llm._history) <= config.MAX_HISTORY_TURNS * 2
    assert llm._history[0]["role"] == "user"
    assert len(llm._history) % 2 == 0


def test_tool_call_round_trip(llm, monkeypatch):
    def plan(m):
        if isinstance(m[-1]["content"], list):
            return end(["Noted, sir."])
        return ["Certainly. "], NS(stop_reason="tool_use", content=[
            NS(type="tool_use", id="t1", name="remember", input={"fact": "Ziad likes Earl Grey"})])
    use_plan(llm, monkeypatch, plan)
    assert llm.think("remember I like Earl Grey") == "Certainly. Noted, sir."
    assert "Earl Grey" in llm._system_prompt()


def test_system_prompt_has_date(llm):
    from datetime import datetime
    assert str(datetime.now().year) in llm._system_prompt()


def test_system_prompt_fixed_within_a_turn(llm, monkeypatch):
    """Thinking blocks are bound to the system prompt, so every tool round in
    one turn must send exactly the same one."""
    systems = []
    calls = iter(["a", "b"])
    monkeypatch.setattr(llm, "_system_prompt", lambda about="": next(calls))

    def stream(**kw):
        systems.append(kw["system"])
        return FakeStream(plan, kw)

    def plan(m):
        if isinstance(m[-1]["content"], list):
            return end(["Done."])
        return [], NS(stop_reason="tool_use", content=[
            NS(type="tool_use", id="t1", name="remember", input={"fact": "x"})])
    monkeypatch.setattr(llm, "_client", NS(messages=NS(stream=stream)))
    llm.think("remember x")
    assert systems == ["a", "a"]


def test_history_notes_tools_used(llm, monkeypatch):
    def plan(m):
        if isinstance(m[-1]["content"], list):
            return end(["Saved, sir."])
        return [], NS(stop_reason="tool_use", content=[
            NS(type="tool_use", id="t1", name="remember", input={"fact": "Ziad likes tea"})])
    use_plan(llm, monkeypatch, plan)
    assert llm.think("remember I like tea") == "Saved, sir."
    saved = llm._history[-1]["content"]
    assert saved.startswith("Saved, sir.") and "[tools used: remember" in saved


def test_empty_reply_not_saved(llm, monkeypatch, capsys):
    use_plan(llm, monkeypatch, lambda m: ([], NS(stop_reason="max_tokens", content=[])))
    assert llm.think("hmm") == ""
    assert llm._history == []
    assert "max_tokens" in capsys.readouterr().out


def test_first_reply_starts_at_a_comma(llm, monkeypatch):
    use_plan(llm, monkeypatch, lambda m: end(["Right away sir, the weather in Courtice, ", "is cold. Wrap up, sir. "]))
    assert list(llm.think_stream("weather")) == [
        "Right away sir, the weather in Courtice,", "is cold.", "Wrap up, sir."]


def test_followup_can_be_ignored(llm, monkeypatch):
    seen = {}

    def plan(m):
        seen["asked"] = m[-1]["content"]
        return end(["[ignore]"])
    client = NS(messages=NS(stream=lambda **kw: (seen.__setitem__("tools", [t["name"] for t in kw["tools"]]),
                                                 FakeStream(plan, kw))[1]))
    monkeypatch.setattr(llm, "_client", client)
    assert list(llm.think_stream("so I told her no", followup=True)) == []
    assert llm.last_ignored
    assert seen["asked"].startswith(llm.FOLLOWUP_NOTE)
    assert "shut_down" not in seen["tools"]
    assert llm._history == []   # overheard chatter isn't saved


def test_followup_answered_when_meant_for_him(llm, monkeypatch):
    use_plan(llm, monkeypatch, lambda m: end(["Tomorrow is sunny, sir."]))
    assert list(llm.think_stream("and tomorrow?", followup=True)) == ["Tomorrow is sunny, sir."]
    assert not llm.last_ignored
    assert llm._history[-2]["content"] == "and tomorrow?"
