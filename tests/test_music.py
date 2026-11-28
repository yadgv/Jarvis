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
    monkeypatch.setattr(config, "MY_PLAYLISTS", [])
    assert music.play_music({}) == "Done." and pressed == ["play"]  # no playlists saved: media key


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


# ---------- "Play some music" -> his saved playlists first ----------
from brain import llm  # noqa: E402

PLAYLISTS = ["The Playlist", "Performative", "Quran"]


@pytest.fixture
def mine(monkeypatch):
    monkeypatch.setattr(config, "MY_PLAYLISTS", list(PLAYLISTS))
    music._offer["at"] = 0.0
    yield
    music._offer["at"] = 0.0


@pytest.mark.parametrize("text", ["Play some music", "play me some music", "Jarvis, play music.",
                                  "can you play some music please", "put on some tunes", "play something",
                                  "I want to listen to some music", "music please"])
def test_generic_music_requests_offer_playlists(mine, text):
    assert music.offer_intent(text)


@pytest.mark.parametrize("text", ["play Blinding Lights", "play some Drake", "pause the music", "play",
                                  "turn the music up", "play my workout playlist", "resume"])
def test_named_music_is_not_offered(mine, text):
    assert not music.offer_intent(text)


def test_no_playlists_no_offer(monkeypatch):
    monkeypatch.setattr(config, "MY_PLAYLISTS", [])
    assert not music.offer_intent("play some music")


def test_question_lists_his_playlists(mine):
    assert music.offer_question() == "Want one of your playlists? The Playlist, Performative, or Quran?"
    assert music.offer_open()


@pytest.mark.parametrize("text,name", [("Performative", "Performative"), ("the playlist", "The Playlist"),
                                       ("play the Quran", "Quran"), ("Koran please", "Quran"),
                                       ("the Quran playlist", "Quran"), ("Performitive", "Performative"),
                                       ("the first one", "The Playlist"), ("the last one", "Quran"),
                                       ("yeah, The Playlist", "The Playlist")])
def test_pick_playlist(mine, text, name):
    assert music.pick_playlist(text) == name


def test_answers_only_count_right_after_the_question(mine, monkeypatch):
    assert music.answer_offer("Performative") is None          # never asked
    music.offer_question()
    assert music.answer_offer("Performative") == ("playlist", "Performative")
    assert music.answer_offer("Quran") is None                 # one answer per question
    music.offer_question()
    assert music.answer_offer("no, just play something") == ("decline", None)
    music.offer_question()
    assert music.answer_offer("play some Drake") is None       # something else: the usual way
    music.offer_question()
    monkeypatch.setattr(music.time, "time", lambda: music._offer["at"] + music.OFFER_SECONDS + 1)
    assert music.answer_offer("Performative") is None          # too late


def test_his_playlist_opens_from_library_not_search(mine, monkeypatch):
    monkeypatch.setattr(pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.ui_automation, "play_library_playlist", lambda app, name: name)
    monkeypatch.setattr(music.ui_automation, "play_in_app",
                        lambda app, q: (_ for _ in ()).throw(AssertionError("searched")))
    assert music.play_music({"query": "the playlist", "kind": "playlist"}) == "Playing The Playlist."


def test_his_playlist_falls_back_to_search(mine, monkeypatch):
    opened, searched = [], []
    monkeypatch.setattr(pc_control, "open_app", lambda a: opened.append(1) or "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.ui_automation, "play_library_playlist", lambda app, name: None)
    monkeypatch.setattr(music.ui_automation, "play_in_app", lambda app, q: searched.append(q) or "Quran")
    assert music.play_music({"query": "Quran", "kind": "playlist"}) == "Playing: Quran."
    assert searched == ["Quran"] and len(opened) == 1          # the app is opened once


def test_model_with_empty_query_gets_the_question(mine):
    out = music.play_music({"query": ""})
    assert out.startswith("Ask him") and "Performative" in out and music.offer_open()


def _no_model(monkeypatch):
    monkeypatch.setattr(llm, "_chain", lambda *a, **k: (_ for _ in ()).throw(AssertionError("model used")))


def test_conversation_asks_then_plays_without_a_model(mine, monkeypatch):
    _no_model(monkeypatch)
    ran = []
    monkeypatch.setattr(llm.skills, "run", lambda name, args: ran.append((name, args)) or "Playing Performative.")
    assert llm.think("play some music") == "Want one of your playlists? The Playlist, Performative, or Quran?"
    assert ran == []
    assert " ".join(llm.think_stream("performative", followup=True)) == "Playing Performative."
    assert ran == [("play_music", {"query": "Performative", "kind": "playlist"})]


def test_conversation_decline_resumes(mine, monkeypatch):
    _no_model(monkeypatch)
    ran = []
    monkeypatch.setattr(llm.skills, "run", lambda name, args: ran.append((name, args)) or "Done.")
    llm.think("put on some music")
    assert " ".join(llm.think_stream("nah", followup=True)).startswith("Okay")
    assert ran == [("media", {"action": "play"})]
