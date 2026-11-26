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


def test_app_shortcut_values(tmp_path):
    import install_app
    v = install_app.shortcut_values(python=r"C:\Python\pythonw3.13.exe")
    assert v["J_TARGET"].endswith("pythonw3.13.exe")
    assert v["J_ARGS"].startswith('"') and v["J_ARGS"].endswith('gui.py"')
    assert v["J_WORKDIR"] == install_app.HERE and v["J_ICON"].endswith("jarvis.ico")


def test_orb_icon(tmp_path):
    import pytest
    pytest.importorskip("PIL")
    import install_app
    path = install_app.make_icon(str(tmp_path / "orb.ico"))
    from PIL import Image
    with Image.open(path) as img:
        assert img.format == "ICO"


def test_app_install_windows_only(monkeypatch):
    import install_app
    monkeypatch.setattr(install_app.sys, "platform", "linux")
    assert "Windows" in install_app.install(login=False)[0]


def test_app_install_makes_both_shortcuts(monkeypatch, tmp_path):
    import install_app
    monkeypatch.setattr(install_app.sys, "platform", "win32")
    monkeypatch.setattr(install_app, "ICON", str(tmp_path / "jarvis.ico"))
    made = []
    monkeypatch.setattr(install_app, "make_shortcut", lambda folder: made.append(folder) or folder + r"\Jarvis.lnk")
    turned = []
    monkeypatch.setattr(install_app.autostart, "turn_on", lambda: turned.append(1) or "on")
    lines = install_app.install(login=True)
    assert made[0] == "DESKTOP" and made[1].endswith("Programs")
    assert turned and lines[-1].startswith("Done")


def test_only_one_jarvis_at_a_time(monkeypatch):
    import socket
    import ui_events as gui
    monkeypatch.setattr(gui, "_INSTANCE_PORT", 0)  # any free port
    monkeypatch.setattr(gui, "_instance_lock", None)
    assert not gui.already_running()
    port = gui._instance_lock.getsockname()[1]
    monkeypatch.setattr(gui, "_INSTANCE_PORT", port)
    lock = gui._instance_lock
    try:
        assert gui.already_running()
    finally:
        lock.close()
    assert isinstance(lock, socket.socket)
