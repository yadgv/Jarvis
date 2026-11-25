import os

import autostart
from skills import system


def test_on_and_off(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert not autostart.is_on()
    assert "start when you log in" in system.start_with_windows({"on": True})
    assert autostart.is_on()
    text = open(autostart.shortcut_path(), encoding="utf-8").read()
    assert "gui.py" in text and "WScript.Shell" in text and ", 0, False" in text
    assert "won't start" in system.start_with_windows({"on": False})
    assert not os.path.exists(autostart.shortcut_path())
    autostart.turn_off()  # already off: no error


def test_windows_only(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert "only works on Windows" in autostart.turn_on()
    assert not autostart.is_on()


def test_prefers_pythonw(tmp_path):
    exe = tmp_path / "python3.13.exe"
    exe.write_text("")
    assert autostart.windowless_python(str(exe)) == str(exe)  # no pythonw next to it
    (tmp_path / "pythonw3.13.exe").write_text("")
    assert autostart.windowless_python(str(exe)) == str(tmp_path / "pythonw3.13.exe")


def test_tee_without_console(tmp_path):
    import main
    tee = main._Tee(None, str(tmp_path / "log.txt"))
    tee.write("hello\n")
    tee.flush()
    assert "hello" in (tmp_path / "log.txt").read_text()
