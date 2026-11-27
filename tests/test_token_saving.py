"""Saving tokens: simple commands and repeat questions need no model, repeat drawings reuse the saved
plan, Claude gets only the relevant tools, and every model call is counted."""
import json
from types import SimpleNamespace as NS

import pytest

import config
from brain import backup, cache, usage
from tests.test_backup import FakeResponse, fake_openrouter, text_chunks


@pytest.fixture
def llm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr(config, "BRAIN_ORDER", ["openrouter"])
    monkeypatch.setattr(config, "QUICK_COMMANDS", True)
    monkeypatch.setattr(config, "ANSWER_CACHE", True)
    from brain import providers
    monkeypatch.setattr(providers, "_resting", {})
    from brain import llm
    llm._history.clear()
    return llm


def no_model(monkeypatch):
    def post(*a, **k):
        raise AssertionError("a model was asked")
    monkeypatch.setattr(backup.requests, "post", post)


# ---------- simple commands ----------
def test_timer_needs_no_model(llm, monkeypatch):
    no_model(monkeypatch)
    ran = []
    monkeypatch.setattr(llm.skills, "run", lambda name, args: ran.append((name, args)) or "Timer set: timer, 5 minutes.")
    assert list(llm.think_stream("set a timer for 5 minutes")) == ["Timer set: timer, 5 minutes."]
    assert ran == [("set_timer", {"seconds": 300})]
    assert "set_timer ->" in llm._history[-1]["content"]          # the history still shows the tool ran
    assert usage.today()["saved"] == 1


@pytest.mark.parametrize("said, tool", [("clear the whiteboard", "whiteboard_step"), ("volume up", "set_volume"),
                                         ("pause the music", "media"), ("open spotify", "open_app")])
def test_common_commands_need_no_model(llm, monkeypatch, said, tool):
    no_model(monkeypatch)
    ran = []
    monkeypatch.setattr(llm.skills, "run", lambda name, args: ran.append(name) or "Done.")
    assert list(llm.think_stream(said)) == ["Done."]
    assert ran == [tool]


def test_next_with_a_drawing_up_is_a_step_not_a_song(llm, monkeypatch):
    from skills import whiteboard
    monkeypatch.setattr(whiteboard, "_board", {"steps": ["one", "two"]})
    ran = []
    monkeypatch.setattr(llm.skills, "run", lambda name, args: ran.append(name) or "Step 2.")
    sent = fake_openrouter(monkeypatch, text_chunks("Step two lights up the signal wire."))
    list(llm.think_stream("next"))
    assert "media" not in ran and len(sent) == 1


def test_the_time_needs_no_model(llm, monkeypatch):
    no_model(monkeypatch)
    [reply] = list(llm.think_stream("what time is it"))
    assert reply.startswith("It's ") and "sir" in reply


def test_a_failed_command_goes_to_the_model_without_running_it_again(llm, monkeypatch):
    ran = []
    monkeypatch.setattr(llm.skills, "run",
                        lambda name, args: ran.append(name) or "I don't know an app called zork. Add it to APPS.")
    sent = fake_openrouter(monkeypatch, text_chunks("There is no Zork app here."))
    assert list(llm.think_stream("open zork")) == ["There is no Zork app here."]
    assert ran == ["open_app"]
    assert "Already done this turn" in sent[0]["messages"][-1]["content"]


def test_overheard_open_still_goes_to_the_model(llm, monkeypatch):
    ran = []
    monkeypatch.setattr(llm.skills, "run", lambda name, args: ran.append(name) or "Opened.")
    fake_openrouter(monkeypatch, text_chunks("[ignore]"))
    list(llm.think_stream("open the door", followup=True))
    assert ran == []


def test_quick_commands_can_be_turned_off(llm, monkeypatch):
    monkeypatch.setattr(config, "QUICK_COMMANDS", False)
    sent = fake_openrouter(monkeypatch, text_chunks("Turning it up, sir."))
    list(llm.think_stream("volume up"))
    assert len(sent) == 1


# ---------- repeat questions ----------
def test_same_question_twice_asks_the_model_once(llm, monkeypatch):
    sent = fake_openrouter(monkeypatch, text_chunks("Sixteen of them."))
    assert list(llm.think_stream("how many ounces in a pound")) == ["Sixteen of them."]
    llm._history.clear()
    assert list(llm.think_stream("How many ounces are in a pound?")) == ["Sixteen of them."]
    assert len(sent) == 1


@pytest.mark.parametrize("said", ["what's the weather like", "what's my name", "what is it", "tell me a joke",
                                  "what do i have today", "who won the game last night", "explain that again",
                                  "open spotify", "what's the latest news"])
def test_never_cached(said):
    assert not cache.cacheable_question(said)


@pytest.mark.parametrize("said", ["how many ounces in a pound", "what's the capital of Peru",
                                  "who wrote Hamlet", "how far is the moon"])
def test_cached(said):
    assert cache.cacheable_question(said)


def test_answers_with_tools_or_questions_back_are_not_saved(llm, monkeypatch):
    fake_openrouter(monkeypatch, text_chunks("Do you mean the country?"), text_chunks("Lima, sir."),
                    text_chunks("Lima, sir."))
    list(llm.think_stream("what's the capital of Peru"))
    list(llm.think_stream("what's the capital of Peru"))      # the first reply was a question: asked again
    list(llm.think_stream("what's the capital of Peru"))      # now saved
    assert cache.get_answer("what's the capital of Peru") == "Lima, sir."


# ---------- repeat drawings and parts ----------
def test_reuse_makes_once_for_the_same_words_in_any_order(monkeypatch):
    monkeypatch.setattr(config, "ANSWER_CACHE", True)
    made = []
    make = lambda: made.append(1) or '{"plan": 1}'
    assert cache.reuse("SYS", "LED wiring to an Arduino Uno", make) == '{"plan": 1}'
    assert cache.reuse("SYS", "arduino uno LEDs wiring", make) == '{"plan": 1}'
    assert cache.reuse("OTHER", "arduino uno LEDs wiring", make) == '{"plan": 1}'   # another job: its own entry
    assert cache.reuse("SYS", "servo wiring to an Arduino Uno", make)
    assert len(made) == 3


def test_reuse_remakes_when_the_saved_one_fails_its_check(monkeypatch):
    monkeypatch.setattr(config, "ANSWER_CACHE", True)
    cache.put_job("SYS", "phone stand", "old")

    def check(text):
        if text == "old":
            raise ValueError("not code")
    assert cache.reuse("SYS", "phone stand", lambda: "new", check) == "new"
    assert cache.get_job("SYS", "phone stand") == "new"


def test_whiteboard_reuses_a_topic_but_not_a_redraw(monkeypatch):
    monkeypatch.setattr(config, "ANSWER_CACHE", True)
    from brain import llm as brain
    from skills import whiteboard
    spec = {"title": "LED", "kind": "wiring", "parts": [{"id": "uno", "type": "arduino_uno"}, {"id": "l", "type": "led"}],
            "wires": [{"from": "uno.D13", "to": "l.+", "step": 1}], "steps": ["Wire it."]}
    calls = []
    monkeypatch.setattr(brain, "complete", lambda *a, **k: calls.append(1) or json.dumps(spec))
    monkeypatch.setattr(whiteboard, "_board", {})
    whiteboard.draw("LED wiring to Arduino")
    whiteboard.draw("Arduino LED wiring")
    assert len(calls) == 1
    monkeypatch.setattr(whiteboard, "_board", {"topic": "LED wiring to Arduino"})
    whiteboard.draw("LED wiring to Arduino")              # "draw it again": a new take
    assert len(calls) == 2


def test_forget_needs_a_key(monkeypatch):
    monkeypatch.setattr(config, "ANSWER_CACHE", True)
    cache.put_job("SYS", "phone stand", "x")
    cache.forget("")
    assert cache.get_job("SYS", "phone stand") == "x"
    cache.forget("job")
    assert cache.get_job("SYS", "phone stand") is None


# ---------- fewer tools ----------
def test_claude_gets_only_the_relevant_tools(llm, monkeypatch):
    import skills
    monkeypatch.setattr(config, "BRAIN_ORDER", ["claude"])
    monkeypatch.setattr(llm, "_claude_off_until", 0.0)
    monkeypatch.setattr(llm.paid, "allowed", lambda: True)
    seen = []

    class Stream:
        def __init__(self, **kw):
            seen.append(kw)
            self.text_stream = iter(["Sixteen, sir. "])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return NS(stop_reason="end_turn", content=[],
                      usage=NS(input_tokens=900, output_tokens=12, cache_read_input_tokens=0,
                               cache_creation_input_tokens=0))
    monkeypatch.setattr(llm, "_client", NS(messages=NS(stream=Stream)))
    list(llm.think_stream("draw me a diagram of a servo on an arduino"))
    names = {t["name"] for t in seen[0]["tools"]}
    assert "show_diagram" in names and len(names) < len(skills.SKILLS) / 2
    assert usage.today()["in"] == 900


# ---------- counting ----------
def test_every_free_model_call_is_counted(llm, monkeypatch):
    fake_openrouter(monkeypatch, text_chunks("Hello, sir."))
    list(llm.think_stream("hello there"))
    day = usage.today()
    assert day["calls"] == 1 and day["in"] > 100 and day["out"] >= 2
    assert "OpenRouter" in day["by"]
    assert "tokens" in usage.summary()


def test_auto_memory_checks_a_sentence_once(monkeypatch):
    from brain import auto_memory
    monkeypatch.setattr(config, "AUTO_MEMORY", True)
    monkeypatch.setattr(auto_memory, "_checked", {})
    said = "my classes are thermodynamics and digital systems"
    assert auto_memory.worth_checking(said, [])
    assert not auto_memory.worth_checking(said, [])


def test_clicking_for_him_keeps_screen_control():
    import skills
    assert "use_computer" in skills.pick_tools("click the submit button on this form")
