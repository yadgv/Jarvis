import json

import config
from brain import memory


def test_history_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    memory.save_history(msgs)
    assert memory.load_history() == msgs


def test_stale_or_corrupt_history_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    (tmp_path / "history.json").write_text(json.dumps(
        {"saved_at": 0, "messages": [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]}))
    assert memory.load_history() == []
    (tmp_path / "history.json").write_text("{garbage")
    assert memory.load_history() == []


def test_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    memory.add_fact("Ziad's sister is called Mona")
    memory.add_fact("ziad's sister is called mona")  # duplicate
    assert memory.load_facts() == ["Ziad's sister is called Mona"]
    assert memory.remove_facts("mona").startswith("Removed 1")
    assert memory.load_facts() == []


def test_junk_facts_are_refused_and_dropped(tmp_path, monkeypatch):
    import config
    from brain import memory
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    assert memory.add_fact("Tuesday").startswith("Not saved")
    assert memory.add_fact("He wants the assistant to remember Tuesday.").startswith("Not saved")
    assert memory.add_fact("His thermo exam is on Tuesday") == "Saved."
    memory._write("facts.json", ["Tuesday", "He wants the assistant to remember Tuesday.", "He lives in Courtice"])
    assert memory.load_facts() == ["He lives in Courtice"]     # old junk from before is left out
