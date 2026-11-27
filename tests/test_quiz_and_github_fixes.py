"""Fixes from the talk test log: GitHub's bare "OK", quiz answers and copied tool notes."""
import json
from types import SimpleNamespace as NS

from brain import backup, llm


class FakeResponse:
    def __init__(self, lines, kind="text/event-stream"):
        self.lines, self.headers, self.status_code, self.encoding = lines, {"content-type": kind}, 200, None

    def iter_lines(self, decode_unicode=True):
        return iter(self.lines)


def test_bare_ok_is_asked_again_without_streaming(monkeypatch):
    sent = []

    def post(messages, exclude=(), target=None):
        sent.append((target.get("extra") or {}).get("stream", True))
        if sent[-1] is False:
            return FakeResponse([json.dumps({"model": "m", "choices": [{"message": {"content": "Hello sir."}}]})],
                                "application/json")
        return FakeResponse(["OK"], "text/plain")
    monkeypatch.setattr(backup, "_post", post)
    backup._NO_STREAM.clear()
    target = {"who": "Github gpt", "rest_key": "github:gpt", "extra": {}}
    out = list(backup.stream_round([{"role": "user", "content": "hi"}], (), target))
    assert out[-1][1][0] == "Hello sir." and sent == [True, False]
    list(backup.stream_round([{"role": "user", "content": "hi"}], (), target))
    assert sent[-1] is False                       # remembered: not streamed to again


def test_github_gets_its_headers():
    from brain import providers
    h = providers._headers("github", "tok")
    assert h["Authorization"] == "Bearer tok" and h["X-GitHub-Api-Version"] == "2022-11-28"
    assert "X-GitHub-Api-Version" not in providers._headers("groq", "tok")


def test_quiz_answer_offers_quiz_next_and_notes_not_spoken():
    import skills
    assert "quiz_next" in skills.FOLLOW_UPS["quiz_me"]
    said = list(llm._sentences(iter(["Correct. [tools used: quiz_me -> Correct. Spot on. Next question: X?]"]), []))
    assert said == ["Correct."]
    said = list(llm._sentences(iter(["Spot on, sir. Next question: Can you define it? Next question: Define it.]"]),
                               []))
    assert said == ["Spot on, sir.", "Next question: Can you define it?"]


def test_quiz_on_a_subject_when_there_is_no_such_file(monkeypatch):
    from skills import files, study
    monkeypatch.setattr(files, "file_text", lambda name: ("", f"No file called {name}."))
    asked = {}

    def complete(system, user, **k):
        asked["user"] = user
        return json.dumps([{"q": "What does the first law say?", "a": "Energy is conserved."}])
    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(study, "_parse", lambda text: [{"q": "What does the first law say?", "a": "Energy."}])
    out = study.quiz_me({"file": "thermo notes"})
    assert "Topic" in asked["user"] and "thermo" in asked["user"] and "notes" not in asked["user"].lower()
    assert "What does the first law say?" in out
    study._quiz.update(cards=[], i=0, right=0, source="", wrong=[])
