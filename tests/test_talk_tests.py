"""Jarvis talks to Jarvis (talk_tests.py), with every model call faked."""
import talk_tests
from brain import llm
from testbench.scenarios import SCENARIOS


def test_a_talk_runs_ends_on_goodbye_and_is_graded(monkeypatch, tmp_path):
    import skills
    lines = iter(["Now make the timer 25 minutes", "cool, that's everything, thanks"])

    def fake_complete(system, user, max_tokens=400, **k):
        if "grade a voice assistant" in system:
            assert "Ziad: Play Blinding Lights" in user and "[tools used: play_music]" in user
            return 'Sure: {"goal_done": true, "score": 4, "problems": ["a bit wordy"]}'
        assert "Your goal:" in system
        return next(lines)

    def fake_think(text, followup=False, **k):
        skills.run("play_music" if "Blinding" in text else "set_timer", {})
        yield "Done, sir."
    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "think_stream", fake_think)
    scenario = dict(SCENARIOS[0], id="t", opener="Play Blinding Lights", expect=["play_music", "set_timer"],
                    avoid=["web_search"], screen=None)
    [r] = talk_tests.run([scenario], delay=0)
    assert r["ok"] and r["score"] == 4 and r["ended"].startswith("conversation closed")
    assert [t["who"] for t in r["transcript"]] == ["Ziad", "Jarvis", "Ziad", "Jarvis", "Ziad"]
    assert r["tools"] == ["play_music", "set_timer"] and r["problems"] == ["a bit wordy"]
    assert not isinstance(skills.run, talk_tests.fakes.Recorder)
    passed, total = talk_tests.report([r], folder=str(tmp_path))
    assert (passed, total) == (1, 1)
    assert "Play Blinding Lights" in next(tmp_path.glob("*.md")).read_text(encoding="utf-8")


def test_missing_tool_and_bad_grade_fail(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda system, user, **k: (
        '{"goal_done": false, "score": 2, "problems": ["never made the slides"]}' if "grade a voice" in system else "<done>"))
    monkeypatch.setattr(llm, "think_stream", lambda text, followup=False, **k: iter(["What topic, sir?"]))
    [r] = talk_tests.run([dict(SCENARIOS[-1], screen=None)], delay=0)
    assert not r["ok"] and r["ended"] == "he finished" and "never used make_document" in r["problems"]


def test_every_scenario_is_well_formed():
    import skills
    names = {s["name"] for s in skills.SKILLS}
    for s in SCENARIOS:
        assert s["goal"] and s["opener"]
        assert set(s.get("expect", [])) <= names and set(s.get("avoid", [])) <= names, s["id"]


def test_no_free_models_left_skips_instead_of_crashing(monkeypatch, tmp_path):
    from brain import backup
    calls = {"n": 0}

    def complete(system, user, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return "<done>"
        raise backup.ProviderError("Github openai/gpt-4.1-mini sent no answer in the reply (OK, text/plain)", "empty")
    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(llm, "think_stream", lambda text, followup=False, **k: iter(["Done, sir."]))
    monkeypatch.setattr(talk_tests.run_tests, "rest_wait", lambda delay, most=120: 0)
    first, second = dict(SCENARIOS[0], id="a", screen=None, expect=[]), dict(SCENARIOS[1], id="b", screen=None)
    results = talk_tests.run([first, second], delay=0)
    assert results[0]["problems"][-1].startswith("not graded: no free models") and results[0]["ok"] is None
    assert results[1]["ok"] is None and results[1]["ended"].startswith("skipped: no free models")
    assert calls["n"] == 3                       # the second talk wasn't even started
    passed, total = talk_tests.report(results, folder=str(tmp_path))
    assert "skipped (no free models left)" in next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
