"""'What did I do today?' from jarvis.log."""
from datetime import datetime, timedelta

import config
from skills import pick_tools, recap


def _log(tmp_path, monkeypatch, lines):
    path = tmp_path / "jarvis.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(config, "LOG_FILE", str(path))


def test_today_from_the_log(tmp_path, monkeypatch):
    today = datetime.now().strftime("%Y-%m-%d")
    yday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    _log(tmp_path, monkeypatch, [
        f"{yday} 22:00:00  You: old stuff  [typed]",
        f"{today} 09:12:03  You: quiz me on my thermo notes  [stt 0.8s]",
        f"{today} 09:12:04  [tool] quiz_me {{'file': 'thermo notes'}}",
        f"{today} 09:12:05  [tool] -> Quiz on thermo ready",
        f"{today} 09:13:00  [tool] quiz_next {{'correct': True}}",
        f"{today} 14:30:00  [brain] something else",
        f"{today} 14:31:00  You: download my statics files  [typed]",
        "a line with no time",
    ])
    out = recap.daily_recap()
    assert "09:12 asked: quiz me on my thermo notes" in out
    assert "quiz_me {'file': 'thermo notes'}" in out
    assert "quiz_next" not in out and "old stuff" not in out and "->" not in out
    assert "download my statics files" in out and "[typed]" not in out
    assert "old stuff" in recap.daily_recap({"day": "yesterday"})


def test_no_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "none.log"))
    assert "nothing" in recap.daily_recap()


def test_offered_for_recap_requests():
    assert "daily_recap" in pick_tools("what did I do today?")
