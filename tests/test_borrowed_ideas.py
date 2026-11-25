"""Ideas adapted from other open-source assistants (GLaDOS, Smart Turn,
openWakeWord, Home Assistant's linux-voice-assistant)."""
import numpy as np

import config
import main
from audio import ducking, recorder, smart_turn
from brain import llm, memory


# 1. Only what he actually said goes into the history when cut off.
def test_heard_part_keeps_the_words_played():
    s = "one two three four five six seven eight nine ten"
    assert main.heard_part(s, 0) == ""
    assert main.heard_part(s, 100) == s
    assert main.heard_part(s, 2 / main.WORDS_PER_SECOND) == "one two"


def test_clip_replaces_last_reply_and_keeps_tool_note(monkeypatch):
    monkeypatch.setattr(memory, "save_history", lambda h: None)
    monkeypatch.setattr(llm, "_history", [
        {"role": "user", "content": "weather?"},
        {"role": "assistant", "content": "It's sunny. Tomorrow rain. [tools used: weather -> ok]"},
    ])
    llm.clip_last_reply("It's sunny.")
    assert llm._history[-1]["content"] == "It's sunny. [interrupted] [tools used: weather -> ok]"


def test_clip_during_turn_is_applied_when_turn_ends(monkeypatch):
    monkeypatch.setattr(memory, "save_history", lambda h: None)
    monkeypatch.setattr(llm, "_history", [])
    monkeypatch.setattr(llm, "_use_claude", lambda: True)

    def fake_turn(asked, system, said, tools_used, exclude=()):
        for s in ["First.", "Second.", "Third."]:
            said.append(s)
            yield s
    monkeypatch.setattr(llm, "_claude_turn", fake_turn)
    gen = llm.think_stream("hi")
    assert next(gen) == "First."
    llm.clip_last_reply("First.")  # cut off while the turn is still running
    list(gen)
    assert llm._history[-1]["content"] == "First. [interrupted]"


# 3. Words said over the beep are kept, but the beep isn't speech.
class Stream:
    def __init__(self, levels):
        self.levels = list(levels)

    def read(self, n):
        level = self.levels.pop(0) if self.levels else 0
        return np.full((n, 1), level, dtype=np.int16), False


def test_beep_is_recorded_but_not_counted_as_speech(monkeypatch):
    monkeypatch.setattr(recorder, "is_speech", lambda c: np.abs(c).mean() > 100)
    monkeypatch.setattr(config, "LISTEN_TIMEOUT", 0.5)
    # Only the beep (3 loud chunks), then quiet: no speech, so nothing recorded.
    audio = recorder.record_until_silence(Stream([3000] * 3), ignore_seconds=0.24)
    assert len(audio) == 0
    # Talking straight through the beep: the beep-time audio is kept.
    audio = recorder.record_until_silence(Stream([3000] * 15), ignore_seconds=0.24)
    assert len(audio) >= 15 * recorder.CHUNK


# 4. Smart Turn: a mid-thought pause doesn't end the turn.
def test_smart_turn_waits_through_a_thinking_pause(monkeypatch):
    monkeypatch.setattr(recorder, "is_speech", lambda c: np.abs(c).mean() > 100)
    monkeypatch.setattr(smart_turn, "load", lambda: True)
    answers = iter([False, False, True])  # "not done", "not done", "done"
    monkeypatch.setattr(smart_turn, "is_finished", lambda a: next(answers))
    you, pause = [3000] * 10, [0] * 40  # 0.8 s talking then 3.2 s quiet
    audio = recorder.record_until_silence(Stream(you + pause))
    # Plain mode would stop 0.6 s into the pause; here the third check ends it.
    assert len(audio) / config.SAMPLE_RATE > 0.8 + 0.6


def test_smart_turn_finished_ends_quickly(monkeypatch):
    monkeypatch.setattr(recorder, "is_speech", lambda c: np.abs(c).mean() > 100)
    monkeypatch.setattr(smart_turn, "load", lambda: True)
    monkeypatch.setattr(smart_turn, "is_finished", lambda a: True)
    audio = recorder.record_until_silence(Stream([3000] * 10 + [0] * 40))
    assert len(audio) / config.SAMPLE_RATE < 0.8 + config.SMART_TURN_SILENCE + 0.1


def test_smart_turn_failure_falls_back_to_plain_pause(monkeypatch):
    monkeypatch.setattr(recorder, "is_speech", lambda c: np.abs(c).mean() > 100)
    monkeypatch.setattr(smart_turn, "load", lambda: True)
    monkeypatch.setattr(smart_turn, "is_finished", lambda a: None)
    audio = recorder.record_until_silence(Stream([3000] * 10 + [0] * 60))
    assert len(audio) / config.SAMPLE_RATE < 0.8 + config.SILENCE_SECONDS + 0.2


def test_smart_turn_input_is_8_seconds_normalised():
    x = smart_turn._prepare(np.ones(16000, dtype=np.float32) * 0.5)
    assert x.shape == (8 * 16000,)
    assert abs(x.mean()) < 1e-4 and abs(x.std() - 1) < 1e-3


# 5. Ducking is harmless where it can't work.
def test_ducking_does_nothing_without_apps(monkeypatch):
    monkeypatch.setattr(config, "DUCK_APPS", [])
    ducking.duck()
    ducking.restore()


# 7. Only relevant facts once there are many.
def test_relevant_facts_picks_matches_and_newest():
    facts = [f"filler fact number {i}" for i in range(40)]
    facts[3] = "His sister is called Mona"
    picked = memory.relevant_facts(facts, "what's my sister's name", limit=8, newest=5)
    assert "His sister is called Mona" in picked
    assert facts[-1] in picked and len(picked) <= 8
    assert memory.relevant_facts(facts[:5], "anything", limit=8) == facts[:5]
