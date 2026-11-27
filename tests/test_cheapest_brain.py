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
    brain.replies.append(says("Right away, sir."))
    list(brain.llm.think_stream("yes"))
    names = {t["function"]["name"] for t in brain.sent[0][1]["tools"]}
    assert "reply_email" in names


def test_never_claims_an_action_no_tool_did(brain, monkeypatch):
    """"Saved and opened, sir" with no tool call: asked again, and it has to use the tool."""
    ran = []
    monkeypatch.setitem(skills._BY_NAME, "open_file", dict(skills._BY_NAME["open_file"], run=lambda a: ran.append(a) or "Opened it."))
    brain.replies += [says("Saved and opened, sir."), calls_tool("open_file", {"path": "phone stand.scad"}),
                      says("Opened it, sir.")]
    out = list(brain.llm.think_stream("open my phone stand file"))
    assert out == ["Opened it, sir."] and ran
    assert any("no tool ran" in str(m.get("content")) for m in brain.sent[1][1]["messages"])


def test_owns_up_if_it_still_does_nothing(brain):
    brain.replies += [says("Done, sir."), says("Done, sir.")]
    out = list(brain.llm.think_stream("open my phone stand file"))
    assert out == ["I haven't actually done that yet, sir. Ask me once more and I will."]


def test_code_and_self_talk_are_never_spoken(brain):
    brain.replies.append(says("Here's the part. ```sc", "ad\ncube([1,2,3]);\n``", "` It is a ",
                              "simple box. I should treat this as him speaking. The open parameter is wrong. ",
                              "<think>hmm</think>Anything else?"))
    out = list(brain.llm.think_stream("show me the code for a box"))
    assert out == ["Here's the part.", "It is a simple box.", "Anything else?"]


def test_model_list_and_lean_models(brain, monkeypatch):
    import ast, os
    src = open(os.path.join(os.path.dirname(config.__file__), "config.py")).read()
    lists = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(src).body
             if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("GROQ_MODELS", "WHITEBOARD_MODELS")}
    assert all("llama-3.3-70b-versatile" not in v for v in lists.values())          # retired by Groq
    monkeypatch.setattr(config, "GROQ_MODELS", ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"])
    monkeypatch.setattr(config, "GROQ_LEAN_MODELS", ["qwen/qwen3.8-27b"])
    big, qwen = providers.groq_targets()
    assert not big["lean"] and qwen["lean"] and qwen["extra"] == {"reasoning_format": "hidden"}


def test_gone_model_rests_a_day(monkeypatch):
    monkeypatch.setattr(providers, "_resting", {})
    e = RuntimeError("Groq x error 404: The model `x` does not exist or you do not have access to it.")
    providers.rest("x", e)
    import time
    assert providers._resting["x"] - time.monotonic() > 23 * 3600


def test_lean_model_gets_fewer_tools_and_turns(brain, monkeypatch):
    monkeypatch.setattr(config, "GROQ_LEAN_MODELS", ["groq-big"])
    for i in range(6):
        brain.llm._history += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": f"a{i}"}]
    brain.replies.append(says("Fine, sir."))
    list(brain.llm.think_stream("what's the weather and remind me to call mum"))
    sent = brain.sent[0][1]
    assert len([m for m in sent["messages"] if m["role"] == "user"]) == 3      # 2 past turns + this one
    assert len(sent["tools"]) <= 6 + len(skills.CORE_TOOLS)


def test_scrap_before_a_tool_call_isnt_spoken(brain, monkeypatch):
    """Seen in his log: the model wrote "You", called remember, then said nothing."""
    ran = []
    monkeypatch.setitem(skills._BY_NAME, "remember", dict(skills._BY_NAME["remember"],
                                                           run=lambda a: ran.append(a) or "Saved."))
    scrap_then_tool = says("You")
    scrap_then_tool.lines = scrap_then_tool.lines[:-1] + calls_tool("remember", {"fact": "x y z"}).lines
    brain.replies += [scrap_then_tool, says()]
    out = list(brain.llm.think_stream("remember my exam is on tuesday"))
    assert ran and out == ["Saved."]


def test_background_job_is_not_started_again_by_the_next_brain(brain, monkeypatch):
    """Groq started the 3D part, then hit a rate limit: the next model mustn't start it again."""
    runs = []
    monkeypatch.setitem(skills._BY_NAME, "make_3d_model", {
        "run": lambda a: runs.append(a) or "Started in the background: Designing the 3D part. Tell him..."})
    brain.replies += [calls_tool("make_3d_model", {"what": "arduino case"}),
                      Resp(status=429, error="Rate limit reached"),
                      says("Designing it now, sir.")]
    out = list(brain.llm.think_stream("make me a 3D model of a case for the Arduino"))
    assert out == ["Designing it now, sir."] and len(runs) == 1
    names = {t["function"]["name"] for t in brain.sent[-1][1].get("tools", [])}
    assert "make_3d_model" not in names


def test_promise_without_a_tool_is_not_spoken(brain, monkeypatch):
    """'Certainly, sir. I am on it right away.' with no tool call made nothing (log, 27 Nov)."""
    monkeypatch.setitem(skills._BY_NAME, "set_timer", {"run": lambda a: "Timer set."})
    brain.replies += [says("Certainly, sir. ", "I am on it right away."),
                      calls_tool("set_timer", {"seconds": 60}), says("Timer set, sir.")]
    out = list(brain.llm.think_stream("set a one minute timer"))
    assert "I am on it right away." not in out and out[-1] == "Timer set, sir."


def test_done_claim_after_only_a_background_start_is_held(brain, monkeypatch):
    """use_computer only *started* (and then failed): 'I've opened the Canvas sign-in window' wasn't true."""
    monkeypatch.setitem(skills._BY_NAME, "use_computer", {
        "run": lambda a: "Started in the background: Working on the screen. Tell him..."})
    brain.replies += [calls_tool("use_computer", {"task": "open canvas sign in"}),
                      says("I've opened the Canvas sign-in window."),
                      says("On it, sir; I'll tell you when the sign-in window is up.")]
    out = list(brain.llm.think_stream("open the canvas sign in"))
    assert out == ["On it, sir; I'll tell you when the sign-in window is up."]
    assert "only started in the background" in json.dumps(brain.sent[-1][1]["messages"])


def test_yes_after_canvas_offer_gets_canvas_sign_in(brain):
    """'Shall I open the Canvas sign-in window?' then 'yes': canvas_sign_in must be on offer."""
    brain.llm._history[:] = [{"role": "user", "content": "download the lecture"},
                             {"role": "assistant", "content": "You're not signed in to Canvas; "
                              "would you like me to open the sign-in window now?"}]
    brain.replies.append(says("Opening it."))
    list(brain.llm.think_stream("yes"))
    names = {t["function"]["name"] for t in brain.sent[0][1]["tools"]}
    assert "canvas_sign_in" in names
