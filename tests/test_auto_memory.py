"""Facts are picked up from conversation without "remember that"."""
import types

import config
from brain import auto_memory, llm, memory


def test_parse_is_forgiving():
    assert auto_memory.parse('Sure! ["His sister is Mona", "He works Saturdays"]') == [
        "His sister is Mona", "He works Saturdays"]
    assert auto_memory.parse("[]") == []
    assert auto_memory.parse("- Likes tea\n- Likes tea\n- Plays piano") == ["Likes tea", "Plays piano"]


def test_skips_short_turns_and_explicit_remember(monkeypatch):
    monkeypatch.setattr(config, "AUTO_MEMORY", True)
    assert not auto_memory.worth_checking("what time is it", [])
    assert not auto_memory.worth_checking("remember that my sister is Mona", ["remember -> Saved."])
    assert auto_memory.worth_checking("my sister Mona is visiting next week", [])
    monkeypatch.setattr(config, "AUTO_MEMORY", False)
    assert not auto_memory.worth_checking("my sister Mona is visiting next week", [])


def test_extract_uses_claude_and_never_raises(monkeypatch):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text='["His sister is Mona"]')])
    monkeypatch.setattr(llm, "_client", types.SimpleNamespace(messages=types.SimpleNamespace(create=create)))
    assert auto_memory.extract("my sister Mona is coming", "Lovely.", ["He likes tea"]) == ["His sister is Mona"]
    assert "He likes tea" in seen["messages"][0]["content"]

    def boom(**kw):
        raise RuntimeError("offline")
    monkeypatch.setattr(llm, "_client", types.SimpleNamespace(messages=types.SimpleNamespace(create=boom)))
    assert auto_memory.extract("x y z w", "", []) == []


def test_saves_in_background(monkeypatch):
    monkeypatch.setattr(config, "AUTO_MEMORY", True)
    saved = []
    monkeypatch.setattr(auto_memory, "extract", lambda u, r, k: ["He works Saturdays"])
    monkeypatch.setattr(memory, "load_facts", lambda: [])
    monkeypatch.setattr(memory, "add_fact", lambda f: saved.append(f) or "Saved.")
    monkeypatch.setattr(auto_memory.threading, "Thread",
                        lambda target, daemon, name: types.SimpleNamespace(start=target))
    auto_memory.run_in_background("I work every Saturday at the store", "Noted.", [])
    assert saved == ["He works Saturdays"]
