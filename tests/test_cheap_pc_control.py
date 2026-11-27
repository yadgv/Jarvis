"""Cheaper PC control: direct actions (tier 1), app controls by name (tier 2),
screenshots only as the fallback (tier 3)."""
import types

import pytest

import config
import skills
from skills import music, quick_actions, ui_automation


# ---------- tier 1 ----------
def test_settings_pages(monkeypatch):
    opened = []
    monkeypatch.setattr(quick_actions, "IS_WINDOWS", True)
    monkeypatch.setattr(quick_actions, "_open", opened.append)
    assert "Opened" in quick_actions.open_settings({"page": "Bluetooth"})
    quick_actions.open_settings({"page": "windows update"})
    quick_actions.open_settings({"page": "the wifi"})
    assert opened == ["ms-settings:bluetooth", "ms-settings:windowsupdate", "ms-settings:network-wifi"]
    assert "No settings page" in quick_actions.open_settings({"page": "teleporter"})


def test_websites_and_searches(monkeypatch):
    urls = []
    monkeypatch.setattr(quick_actions.webbrowser, "open", urls.append)
    quick_actions.open_website({"site": "YouTube", "search": "lo-fi music"})
    quick_actions.open_website({"site": "netflix"})
    quick_actions.open_website({"site": "bbc.co.uk"})
    quick_actions.open_website({"site": "best pizza in Courtice"})
    assert urls == ["https://www.youtube.com/results?search_query=lo-fi+music", "https://www.netflix.com",
                    "https://bbc.co.uk", "https://www.google.com/search?q=best+pizza+in+Courtice"]


def test_dark_mode(monkeypatch):
    seen = []
    monkeypatch.setattr(quick_actions, "IS_WINDOWS", True)
    monkeypatch.setattr(quick_actions, "_set_dark_mode", seen.append)
    assert quick_actions.dark_mode({"on": False}) == "Dark mode off."
    assert seen == [False]


# ---------- tier 2 ----------
class C:
    """A fake UI Automation control."""
    def __init__(self, kind, name, kids=(), patterns=(), offscreen=False):
        self.ControlTypeName, self.Name, self.kids = kind + "Control", name, list(kids)
        self.patterns, self.IsOffscreen, self.log = set(patterns), offscreen, []

    def GetChildren(self):
        return self.kids

    def GetPattern(self, pid):
        if pid not in self.patterns:
            return None
        ctl = self
        return types.SimpleNamespace(Invoke=lambda: ctl.log.append("invoke"), Select=lambda: ctl.log.append("select"),
                                     Toggle=lambda: ctl.log.append("toggle"),
                                     SetValue=lambda v: ctl.log.append(("value", v)))

    def SetFocus(self):
        pass

    def SendKeys(self, keys):
        self.log.append(("keys", keys))

    def Click(self):
        self.log.append("click")

    def DoubleClick(self):
        self.log.append("double")

    def SetActive(self):
        pass


@pytest.fixture
def desktop(monkeypatch):
    search = C("Edit", "Search", patterns={ui_automation.VALUE})
    send = C("Button", "Send", patterns={ui_automation.INVOKE})
    play = C("Button", "Play", patterns={ui_automation.INVOKE})
    win = C("Window", "Apple Music", [C("Pane", "", [search, play, send, C("Button", "Hidden", offscreen=True),
                                                       C("Text", "Now playing: nothing")])])
    root = C("Pane", "Desktop", [C("Window", "Settings"), win])
    fake = types.SimpleNamespace(GetRootControl=lambda: root)
    monkeypatch.setattr(ui_automation, "_auto", lambda: fake)
    monkeypatch.setattr(ui_automation, "IS_WINDOWS", True)
    monkeypatch.setattr(ui_automation, "_pending_click", None)
    monkeypatch.setattr(ui_automation.time, "sleep", lambda s: None)
    return types.SimpleNamespace(win=win, search=search, send=send, play=play)


def test_lists_controls_as_text(desktop):
    out = ui_automation.app_controls({"app": "apple music", "action": "list"})
    assert "Edit: Search" in out and "Button: Play" in out and "Text: Now playing: nothing" in out
    assert "Hidden" not in out


def test_click_and_type_by_name(desktop):
    assert ui_automation.app_controls({"app": "Apple Music", "action": "click", "name": "play"}) == \
        "Clicked Button 'Play'."
    assert desktop.play.log == ["invoke"]
    ui_automation.app_controls({"app": "music", "action": "type", "text": "Drake", "press_enter": True})
    assert desktop.search.log == [("value", "Drake"), ("keys", "{Enter}")]
    assert "No open window" in ui_automation.app_controls({"app": "photoshop", "action": "list"})


def test_risky_click_needs_a_yes_in_a_later_turn(desktop, monkeypatch):
    monkeypatch.setattr(skills, "turn", 3)
    click = {"app": "apple music", "action": "click", "name": "send"}
    assert ui_automation.app_controls(click).startswith("CONFIRM")
    assert ui_automation.app_controls({**click, "confirmed": True}).startswith("CONFIRM")  # same turn
    monkeypatch.setattr(skills, "turn", 4)
    assert ui_automation.app_controls({**click, "confirmed": True}) == "Clicked Button 'Send'."
    assert desktop.send.log == ["invoke"]


def test_music_plays_by_name_without_screenshots(desktop, monkeypatch):
    song = C("ListItem", "Blinding Lights, The Weeknd", [C("Button", "Play Blinding Lights",
                                                          patterns={ui_automation.INVOKE})])

    def after_search(v):
        desktop.search.log.append(("value", v))
        desktop.win.kids.append(song)
        desktop.win.kids.append(C("Button", "Pause"))
    desktop.search.GetPattern = lambda pid: types.SimpleNamespace(SetValue=after_search)
    monkeypatch.setattr(music.pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.computer, "use_computer", lambda a: pytest.fail("used screenshots"))
    assert music.play_music({"query": "Blinding Lights"}) == "Playing: Blinding Lights, The Weeknd."
    assert song.kids[0].log == ["invoke"]


def test_music_falls_back_to_screenshots(desktop, monkeypatch):
    monkeypatch.setattr(music.config, "MUSIC_SCREEN_CONTROL", True, raising=False)
    monkeypatch.setattr(music.pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.computer, "use_computer", lambda a: "Playing via screen.")
    assert music.play_music({"query": "Some Unknown Song"}) == "Playing via screen."


def test_artist_page_play_then_media_key_before_screenshots(desktop, monkeypatch):
    """An artist result opens a page: press its Play; if still not playing, the media key."""
    artist = C("ListItem", "Drake, Artist", patterns={ui_automation.INVOKE})
    page_play = C("Button", "Play", patterns={ui_automation.INVOKE})
    pressed = []

    def after_search(v):
        desktop.win.kids.append(artist)
    desktop.search.GetPattern = lambda pid: types.SimpleNamespace(SetValue=after_search)
    desktop.win.kids[0].kids.remove(desktop.play)
    artist.DoubleClick = lambda: desktop.win.kids.append(page_play)
    monkeypatch.setattr(music.pc_control, "_press",
                        lambda key, times=1: pressed.append(key) or desktop.win.kids.append(C("Button", "Pause")))
    monkeypatch.setattr(music.pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.computer, "use_computer", lambda a: pytest.fail("used screenshots"))
    assert music.play_music({"query": "Drake", "kind": "artist"}) == "Playing: Drake, Artist."
    assert page_play.log == ["invoke"] and pressed == ["play_pause"]


def test_tier_two_says_why_it_gave_up(desktop, monkeypatch, capsys):
    monkeypatch.setattr(music.pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.computer, "use_computer", lambda a: "Playing via screen.")
    music.play_music({"query": "Some Unknown Song"})
    assert "no result named like 'Some Unknown Song'" in capsys.readouterr().out


# ---------- tier 3 ----------
def test_screen_control_logs_tokens(capsys):
    from skills import computer
    computer._tokens.update(input=0, output=0, steps=0)
    computer._count(types.SimpleNamespace(usage=types.SimpleNamespace(
        input_tokens=1200, output_tokens=80, cache_read_input_tokens=3000, cache_creation_input_tokens=0)))
    computer._count(types.SimpleNamespace())
    assert computer._tokens == {"input": 4200, "output": 80, "steps": 2}


def test_use_computer_says_last_resort():
    desc = next(s for s in skills.SKILLS if s["name"] == "use_computer")["description"]
    assert desc.startswith("LAST RESORT") and "app_controls" in desc and "open_website" in desc
    assert config.MUSIC_APP


def test_tier_two_reads_the_window_again_if_it_changed(desktop, monkeypatch, capsys):
    """Apple Music still opening: UI Automation says the element went away (0x80040200)."""
    calls = []
    real = ui_automation._walk

    def flaky(top):
        if not calls:
            calls.append(1)
            raise OSError(-2147220992, None, (None, None, None, 0, None))
        return real(top)
    monkeypatch.setattr(ui_automation, "_walk", flaky)
    monkeypatch.setattr(music.pc_control, "open_app", lambda a: "Opened apple music.")
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.computer, "use_computer", lambda a: "Playing via screen.")
    music.play_music({"query": "Some Unknown Song"})
    out = capsys.readouterr().out
    assert "trying once more" in out and "no result named like" in out
