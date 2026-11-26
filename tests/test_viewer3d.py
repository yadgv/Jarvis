"""Jarvis's own 3D viewer: serves the part to its page; OpenSCAD only on request."""
import json
import struct
import urllib.request

import pytest

from skills import viewer3d


def _stl(path):
    tri = struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 10, 0, 0, 0, 20, 5, 0)
    path.write_bytes(b"\0" * 80 + struct.pack("<I", 1) + tri)
    return str(path)


@pytest.fixture
def viewer(monkeypatch):
    opened = []
    monkeypatch.setattr(viewer3d, "open_window", lambda: opened.append(True))
    monkeypatch.setattr(viewer3d, "_part", {"version": 0, "name": "", "stl": "", "scad": ""})
    return opened


def _get(path):
    with urllib.request.urlopen(viewer3d.url() + path.lstrip("/"), timeout=5) as r:
        return r.read()


def test_show_serves_the_part(viewer, tmp_path):
    stl = _stl(tmp_path / "bracket.stl")
    scad = tmp_path / "bracket.scad"
    scad.write_text("cube(10);")
    viewer3d.show(stl, "bracket", str(scad))
    assert viewer
    info = json.loads(_get("/info.json"))
    assert info == {"version": 1, "name": "bracket", "has_model": True, "openscad": True}
    assert _get("/model.stl") == open(stl, "rb").read()
    page = _get("/").decode()
    assert "Jarvis 3D viewer" in page and "webgl" in page and "Open in OpenSCAD" in page
    viewer3d.show(stl, "bracket v2", str(scad))
    assert json.loads(_get("/info.json"))["version"] == 2       # the open page reloads it


def test_open_in_openscad_uses_the_window_app(viewer, tmp_path, monkeypatch):
    from skills import cad
    scad = tmp_path / "a.scad"
    scad.write_text("cube(1);")
    viewer3d.show(_stl(tmp_path / "a.stl"), "a", str(scad))
    ran = []
    monkeypatch.setattr(cad, "_exe", lambda: "C:/OpenSCAD/openscad.com")
    monkeypatch.setattr(cad, "_gui", lambda exe: exe.replace(".com", ".exe"))
    monkeypatch.setattr(viewer3d.subprocess, "Popen", lambda cmd, **k: ran.append(cmd))
    assert viewer3d.open_in_openscad() == "Opened in OpenSCAD."
    assert ran == [["C:/OpenSCAD/openscad.exe", str(scad)]]
    monkeypatch.setattr(cad, "_exe", lambda: None)
    assert "isn't installed" in viewer3d.open_in_openscad()


def test_show_without_a_part(viewer, monkeypatch):
    from skills import cad
    monkeypatch.setitem(cad._last, "path", None)
    assert "no 3D part" in viewer3d.show_3d_model()


def test_tools_are_offered_for_3d_requests():
    import skills
    for ask in ("open it in openscad", "show me the 3d model again"):
        tools = skills.pick_tools(ask)
        assert "show_3d_model" in tools and "open_in_openscad" in tools, ask
