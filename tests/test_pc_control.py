import config
import skills
from skills import pc_control


def test_windows_keys(monkeypatch):
    pressed = []
    monkeypatch.setattr(pc_control, "IS_WINDOWS", True)
    monkeypatch.setattr(pc_control, "_press", lambda key, times=1: pressed.append((key, times)))
    assert skills.run("set_volume", {"action": "up", "amount": 20}) == "Volume up 20%."
    assert skills.run("set_volume", {"action": "set", "level": 30}) == "Volume set to 30%."
    assert pressed[-2:] == [("volume_down", 50), ("volume_up", 15)]
    assert skills.run("media", {"action": "pause"}) == "Done."
    assert pressed[-1] == ("play_pause", 1)
    assert "Say" in skills.run("media", {"action": "rewind"})


def test_open_app_from_config_and_start_menu(monkeypatch):
    opened = []
    monkeypatch.setattr(pc_control, "IS_WINDOWS", True)
    monkeypatch.setattr(pc_control.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(pc_control, "_start_menu_shortcuts", lambda: {
        "spotify": r"C:\sm\Spotify.lnk", "microsoft word": r"C:\sm\Word.lnk", "uninstall word": r"C:\sm\u.lnk"})
    assert skills.run("open_app", {"name": "Calculator"}) == "Opened calculator."
    assert skills.run("open_app", {"name": "spotify"}) == "Opened spotify."
    assert skills.run("open_app", {"name": "word"}) == "Opened word."
    assert opened == [config.APPS["calculator"], r"C:\sm\Spotify.lnk", r"C:\sm\Word.lnk"]
    assert "don't know" in skills.run("open_app", {"name": "rm -rf"})


def test_linux_without_tools(monkeypatch):
    monkeypatch.setattr(pc_control, "IS_WINDOWS", False)
    monkeypatch.setattr(pc_control.shutil, "which", lambda c: None)
    assert "isn't available" in skills.run("set_volume", {"action": "up"})
    assert "isn't available" in skills.run("media", {"action": "next"})
