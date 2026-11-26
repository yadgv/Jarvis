"""The conversation test bench (run_tests.py) itself."""
import run_tests
from brain import llm
from testbench.cases import CASES


def test_every_case_passes_offline(tmp_path):
    results = run_tests.run(CASES, live=False, delay=0)
    fails = [(r["case"], r["problems"]) for r in results if not r["ok"]]
    assert not fails
    passed, total = run_tests.report(results, False, folder=str(tmp_path))
    assert passed == total and list(tmp_path.glob("*.md")) and list(tmp_path.glob("*.json"))


def test_live_mode_records_tools_and_scores(monkeypatch, tmp_path):
    import skills

    def fake_chain(asked, system, said, tools_used, exclude=(), history=None, can_ask=True):
        skills.run("set_timer", {"minutes": 10})   # sets a timer whatever he asked
        said.append("Timer set, sir.")
        yield "Timer set, sir."

    monkeypatch.setattr(llm, "_chain", fake_chain)
    monkeypatch.setattr(llm.local_llm, "should_use", lambda *a, **k: False)
    monkeypatch.setattr(llm.network, "online", lambda: True)
    monkeypatch.setattr(llm.memory, "save_history", lambda *a, **k: None)
    cases = [c for c in CASES if c["id"] in ("timer", "chat-joke")]
    rows = {r["case"]: r for r in run_tests.run(cases, live=True, delay=0)}
    assert rows["timer"]["ok"] and rows["timer"]["tools"] == ["set_timer"]
    assert rows["timer"]["args"] == [{"minutes": 10}]
    assert not rows["chat-joke"]["ok"]          # it set a timer when no tool was wanted
    assert not isinstance(skills.run, run_tests.fakes.Recorder)   # put back afterwards


def test_screen_is_faked_and_put_back():
    from skills import sight
    real = sight.read
    run_tests.run([c for c in CASES if c["id"] == "brief-article"], live=False, delay=0)
    assert sight.read is real and not sight.last["text"]
