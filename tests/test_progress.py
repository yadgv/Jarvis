"""Long tools get short spoken progress lines; quick ones don't."""
import threading
import time

import skills


def test_slow_tool_gets_a_filler_and_tool_can_narrate(monkeypatch):
    monkeypatch.setattr(skills, "PROGRESS_AFTER", 0.05)
    lines = []

    def slow(a):
        skills.progress("Opening Chrome now.")
        time.sleep(0.2)
        return "done"
    skills.register([{"name": "slow_test_tool", "description": "", "parameters": {}, "run": slow}])
    skills.set_progress_handler(lines.append)
    try:
        assert skills.run("slow_test_tool", {}) == "done"
    finally:
        skills.set_progress_handler(None)
    assert lines == ["Opening Chrome now.", "One moment, sir."]


def test_quick_tool_and_other_threads_stay_quiet(monkeypatch):
    monkeypatch.setattr(skills, "PROGRESS_AFTER", 0.05)
    lines = []
    skills.register([{"name": "quick_test_tool", "description": "", "parameters": {},
                      "run": lambda a: skills.progress("hi") or "ok"}])
    assert skills.run("quick_test_tool", {}) == "ok"  # no handler on this thread
    skills.set_progress_handler(lines.append)
    t = threading.Thread(target=lambda: skills.run("quick_test_tool", {}))  # e.g. a Telegram turn
    t.start()
    t.join()
    skills.set_progress_handler(None)
    assert lines == []


def test_progress_is_spoken_but_not_remembered(monkeypatch):
    import main
    played, clipped = [], []

    def think(text):
        yield "Let me check."
        skills.progress("Still looking, sir.")
        yield "Found it."
    monkeypatch.setattr(main, "think_stream", think)
    monkeypatch.setattr(main.tts, "synthesize", lambda s: (s, 1))
    monkeypatch.setattr(main.tts, "play", lambda clip: played.append(clip[0]))
    monkeypatch.setattr(main, "clip_last_reply", clipped.append)
    main.respond("hi")
    assert played == ["Let me check.", "Still looking, sir.", "Found it."]
    assert not clipped
