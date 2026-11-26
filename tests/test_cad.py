"""3D printable parts as OpenSCAD files."""
import os

import pytest

import config
from skills import cad, files

CODE = """Here is the part:
```openscad
// Phone stand
$fn = 64;
width = 80; // phone width
depth = 60;
angle = 65;
difference() {
  cube([width, depth, 8]);
  translate([5, 5, 4]) cube([width - 10, 10, 10]);
}
```"""


@pytest.fixture
def model(monkeypatch):
    asked = []
    from brain import llm
    monkeypatch.setattr(llm, "complete", lambda system, user, **k: asked.append((system, user, k)) or CODE)
    monkeypatch.setattr(cad, "_last", {"path": None, "code": None, "what": None})
    return asked


def test_clean_keeps_only_safe_code():
    code = cad.clean(CODE)
    assert code.startswith("// Phone stand") and "```" not in code
    for bad in ("Sorry, I can't.", 'include <BOSL2/std.scad>\ncube(1);', 'import("C:/secret.stl");',
                "cube([1, 2, 3]);\ndifference() {", "surface(file = \"x.dat\");"):
        with pytest.raises(ValueError):
            cad.clean(bad)


def test_saves_scad_without_openscad(model, monkeypatch):
    monkeypatch.setattr(cad, "_exe", lambda: None)
    out = cad.make_3d_model({"what": "phone stand"})
    path = os.path.join(files._folder("documents"), "Jarvis 3D", "phone stand.scad")
    assert os.path.isfile(path) and "cube([width" in open(path).read()
    assert "OpenSCAD isn't installed" in out and "width 80 mm" in out
    system, user, k = model[0]
    assert "OpenSCAD" in system and "millimetres" in system and k["models"] == config.WHITEBOARD_MODELS
    import json
    with open(files._undo_path()) as f:
        assert json.load(f)[-1]["moves"] == [["", path]]      # "undo that" bins it


def test_change_uses_the_last_part(model, monkeypatch):
    monkeypatch.setattr(cad, "_exe", lambda: None)
    assert "no part to change" in cad.make_3d_model({"change": "make it taller"})
    cad.make_3d_model({"what": "phone stand"})
    cad.make_3d_model({"change": "make it 10 mm taller"})
    assert "Here is the OpenSCAD for phone stand" in model[1][1] and "10 mm taller" in model[1][1]
    folder = os.path.join(files._folder("documents"), "Jarvis 3D")
    assert sorted(os.listdir(folder)) == ["phone stand (2).scad", "phone stand.scad"]


def test_with_openscad_exports_stl_and_previews(model, monkeypatch):
    monkeypatch.setattr(cad, "_exe", lambda: "openscad")
    ran, shown, opened = [], [], []

    def render(exe, scad, out, extra=()):
        ran.append((out, list(extra)))
        with open(out, "wb") as f:
            f.write(b"\x89PNG fake" if out.endswith(".png") else b"solid part")
        return ""
    monkeypatch.setattr(cad, "_render", render)
    from skills import whiteboard
    monkeypatch.setattr(whiteboard, "show_svg", lambda title, svg, steps, topic="": shown.append(svg))
    monkeypatch.setattr(cad.subprocess, "Popen", lambda cmd, **k: opened.append(cmd))
    out = cad.make_3d_model({"what": "phone stand"})
    assert ran[0][0].endswith("phone stand.stl") and ran[1][0].endswith(".png")
    assert "STL for the slicer" in out and "preview is on the whiteboard" in out and "open in OpenSCAD" in out
    assert "data:image/png;base64," in shown[0]
    assert opened and opened[0][1].endswith("phone stand.scad")


def test_build_errors_are_reported(model, monkeypatch):
    monkeypatch.setattr(cad, "_exe", lambda: "openscad")
    monkeypatch.setattr(cad, "_render", lambda *a, **k: "ERROR: Parser error in line 3")
    out = cad.make_3d_model({"what": "phone stand"})
    assert "couldn't build it" in out and "Parser error" in out and "change" in out


def test_3d_printing_asks_get_the_tool():
    import skills
    for ask in ("make me a 3d printable phone stand", "design a bracket for my servo", "make it 10 mm taller",
                "export an stl of a box"):
        assert "make_3d_model" in skills.pick_tools(ask), ask
    assert "make_3d_model" in skills.NEEDS_INTERNET
