import pytest

import config
from skills import computer, music, pc_control, quick_actions


@pytest.fixture(autouse=True)
def screen_control(monkeypatch):
    monkeypatch.setattr(config, "MUSIC_SCREEN_CONTROL", True, raising=False)


def test_play_music_opens_app_and_searches(monkeypatch):
    opened, tasks = [], []
    monkeypatch.setattr(pc_control, "open_app", lambda a: opened.append(a["name"]) or "Opened apple music.")
    monkeypatch.setattr(computer, "use_computer", lambda a: tasks.append(a["task"]) or "Blinding Lights by The Weeknd")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    out = music.play_music({"query": "Blinding Lights", "kind": "song"})
    assert out == "Blinding Lights by The Weeknd"
    assert opened == ["apple music"]
    assert "'Blinding Lights'" in tasks[0] and "no need to ask for confirmation" in tasks[0]


def test_playlist_looks_in_library_first(monkeypatch):
    tasks = []
    monkeypatch.setattr(pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(computer, "use_computer", lambda a: tasks.append(a["task"]) or "ok")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    music.play_music({"query": "Gym", "kind": "playlist"})
    assert "Library > Playlists" in tasks[0]


def test_app_missing(monkeypatch):
    monkeypatch.setattr(pc_control, "open_app", lambda a: "I don't know an app called apple music.")
    monkeypatch.setattr(quick_actions, "open_website", lambda a: "Opened https://www.youtube.com/watch?v=x.")
    assert "YouTube" in music.play_music({"query": "x"})
    pressed = []
    monkeypatch.setattr(pc_control, "media", lambda a: pressed.append(a["action"]) or "Done.")
    assert music.play_music({}) == "Done." and pressed == ["play"]  # "play some music": media key


def test_no_paid_screen_control_by_default_youtube_instead(monkeypatch):
    monkeypatch.setattr(config, "MUSIC_SCREEN_CONTROL", False)
    monkeypatch.setattr(pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.ui_automation, "play_in_app", lambda app, q: "")
    monkeypatch.setattr(computer, "use_computer", lambda a: (_ for _ in ()).throw(AssertionError("paid")))
    sent = []
    monkeypatch.setattr(quick_actions, "open_website", lambda a: sent.append(a) or "Opened it.")
    assert "YouTube" in music.play_music({"query": "Never Gonna Give You Up"})
    assert sent == [{"site": "youtube", "search": "Never Gonna Give You Up", "play": True}]
