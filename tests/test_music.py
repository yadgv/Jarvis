from skills import computer, music, pc_control


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
    assert music.play_music({"query": "x"}).startswith("I don't know")
    assert music.play_music({}) == "What should I play?"
