"""Voice and personality settings changed by voice."""
import pytest

import config
from brain import settings
from skills import personality


@pytest.fixture(autouse=True)
def tmp_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "VOICES", {"jarvis": "id-1", "deep": "id-2"})


def test_defaults_sound_like_the_butler():
    text = settings.prompt_lines()
    assert "butler" in text and "1-3 sentences" in text and "never 'sir'" not in text
    assert settings.speed() == 1.0 and settings.voice_id() == "id-1"


def test_changes_are_saved_and_used():
    assert "Saved" in personality.change_setting({"setting": "style", "value": "Casual"})
    assert "Saved" in personality.change_setting({"setting": "call me", "value": "Ziad"})
    assert "Saved" in personality.change_setting({"setting": "speed", "value": "1.2"})
    assert "Saved" in personality.change_setting({"setting": "voice", "value": "deep"})
    text = settings.prompt_lines()
    assert "casually" in text and "'Ziad'" in text and "never 'sir'" in text
    assert settings.speed() == 1.2 and settings.voice_id() == "id-2"
    assert "casual" in personality.get_settings()
    assert "defaults" in personality.change_setting({"setting": "reset"})
    assert settings.get("style") == "butler"


def test_bad_values_are_refused():
    assert "Unknown style" in personality.change_setting({"setting": "style", "value": "pirate"})
    assert "Unknown voice" in personality.change_setting({"setting": "voice", "value": "morgan"})
    assert "must be a number" in personality.change_setting({"setting": "speed", "value": "fast"})
    personality.change_setting({"setting": "speed", "value": "9"})
    assert settings.speed() == settings.MAX_SPEED
    personality.change_setting({"setting": "call_me", "value": "nothing"})
    assert "Don't use 'sir'" in settings.prompt_lines()


def test_fish_request_uses_speed_and_voice(monkeypatch):
    from audio import tts
    personality.change_setting({"setting": "speed", "value": "0.8"})
    seen = {}
    monkeypatch.setattr(tts._http, "post", lambda url, **k: seen.update(k["json"]))
    tts._fish_request("hello", stream=False)
    assert seen["prosody"]["speed"] == 0.8 and seen["reference_id"] == "id-1"
