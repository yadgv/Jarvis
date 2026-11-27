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


def test_with_openscad_exports_stl_and_shows_it_in_the_viewer(model, monkeypatch):
    monkeypatch.setattr(cad, "_exe", lambda: "openscad")
    ran, shown, opened = [], [], []

    def render(exe, scad, out, extra=()):
        ran.append((out, list(extra)))
        with open(out, "wb") as f:
            f.write(b"solid part")
        return ""
    monkeypatch.setattr(cad, "_render", render)
    from skills import viewer3d
    monkeypatch.setattr(viewer3d, "open_window", lambda: shown.append(viewer3d.info()))
    monkeypatch.setattr(cad.subprocess, "Popen", lambda cmd, **k: opened.append(cmd))
    out = cad.make_3d_model({"what": "phone stand"})
    assert len(ran) == 1 and ran[0][0].endswith("phone stand.stl")     # no PNG preview needed
    assert "STL for the slicer" in out and "3D viewer" in out and "OpenSCAD" not in out
    assert shown and shown[0]["name"] == "phone stand" and shown[0]["has_model"] and shown[0]["openscad"]
    assert not opened                                                   # OpenSCAD's window only when asked
    cad.make_3d_model({"what": "phone stand", "open": True})
    assert opened and opened[0][1].endswith(".scad")


def test_build_errors_are_fixed_once_then_reported(model, monkeypatch):
    monkeypatch.setattr(cad, "_exe", lambda: "openscad")
    tries = []
    monkeypatch.setattr(cad, "_render", lambda *a, **k: tries.append(a) or "ERROR: Parser error in line 3")
    out = cad.make_3d_model({"what": "phone stand"})
    assert len(tries) == 1 + cad.FIX_TRIES                   # built, then fixed by the model up to 3 times
    assert "fix it: ERROR: Parser error in line 3" in model[1][1]
    assert "couldn't build it" in out and "Parser error" in out and "in the log" in out


def test_a_fixed_part_builds(model, monkeypatch, tmp_path):
    monkeypatch.setattr(cad, "_exe", lambda: "openscad")
    results = iter(["ERROR: Parser error in line 3", "", ""])

    def render(exe, scad, out, extra=()):
        r = next(results)
        if not r:
            open(out, "wb").write(b"x")
        return r
    monkeypatch.setattr(cad, "_render", render)
    monkeypatch.setattr(cad, "_preview", lambda *a: False)
    monkeypatch.setattr(cad.subprocess, "Popen", lambda cmd, **k: None)
    assert "STL for the slicer" in cad.make_3d_model({"what": "phone stand"})


def test_windows_uses_the_console_openscad(tmp_path, monkeypatch):
    folder = tmp_path / "OpenSCAD"
    folder.mkdir()
    for name in ("openscad.exe", "openscad.com"):
        (folder / name).write_text("")
    assert cad._console(str(folder / "openscad.exe")) == str(folder / "openscad.com")
    assert cad._gui(str(folder / "openscad.com")) == str(folder / "openscad.exe")
    monkeypatch.setattr(cad.shutil, "which", lambda n: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert cad._exe() == str(folder / "openscad.com")


def test_render_logs_everything(tmp_path, monkeypatch, capsys):
    import subprocess
    monkeypatch.setattr(cad.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(
        cmd, 1, "", "Parsing design...\nERROR: Parser error: syntax error in file part (2).scad, line 7\n"))
    err = cad._render("C:/OpenSCAD/openscad.com", str(tmp_path / "part (2).scad"), str(tmp_path / "part (2).stl"))
    assert err.startswith("ERROR: Parser error") and "line 7" in err
    log = capsys.readouterr().out
    assert "exit 1" in log and "NO FILE" in log and '"' in log and "line 7" in log   # quoted path, full error
    monkeypatch.setattr(cad.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", ""))
    assert "window app" in cad._render("C:/OpenSCAD/openscad.exe", "a.scad", str(tmp_path / "a.stl"))
    # A made-up module draws nothing: OpenSCAD only warns, then makes no file.
    monkeypatch.setattr(cad.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(
        cmd, 1, "", "WARNING: Ignoring unknown module 'rounded_cube' in file a.scad, line 2\n"
                    "Current top level object is empty.\n"))
    assert "unknown module 'rounded_cube'" in cad._render("openscad", "a.scad", str(tmp_path / "a.stl"))


def test_3d_printing_asks_get_the_tool():
    import skills
    for ask in ("make me a 3d printable phone stand", "design a bracket for my servo", "make it 10 mm taller",
                "export an stl of a box"):
        assert "make_3d_model" in skills.pick_tools(ask), ask
    assert "make_3d_model" in skills.NEEDS_INTERNET


def test_open_file_uses_openscad_for_scad(monkeypatch, private_files):
    path = private_files / "Documents" / "Jarvis 3D"
    path.mkdir()
    (path / "phone stand.scad").write_text("cube(1);")
    monkeypatch.setattr(cad, "_exe", lambda: "C:/OpenSCAD/openscad.com")
    launched = []
    monkeypatch.setattr(files.subprocess, "Popen", lambda cmd, **k: launched.append(cmd))
    out = files.open_file({"path": "phone stand.scad"})
    assert "in OpenSCAD" in out and launched[0][1].endswith("phone stand.scad")


def test_design_skips_chatty_models_and_falls_back_to_claude(monkeypatch):
    """A free model that answers with chat instead of code is skipped; Claude writes it last."""
    import types
    from brain import llm, providers, backup, network
    monkeypatch.setattr(network, "online", lambda: True)
    monkeypatch.setattr(providers, "order", lambda: ["groq", "claude"])
    monkeypatch.setattr(providers, "groq_targets", lambda **k: [{"model": "free-a", "who": "free-a"},
                                                                 {"model": "free-b", "who": "free-b"}])
    answers = {"free-a": "Here's a phone stand you can paste into OpenSCAD!",
               "free-b": "<think>let me think about cube( sizes</think>Sure, sir."}
    monkeypatch.setattr(backup, "stream_round", lambda m, e, t: iter([("text", answers[t["model"]])]))
    monkeypatch.setattr(llm, "_use_claude", lambda: True)
    asked = []
    msg = types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=CODE)])
    monkeypatch.setattr(llm, "_client", types.SimpleNamespace(messages=types.SimpleNamespace(
        create=lambda **k: asked.append(k) or msg)))
    monkeypatch.setattr(cad, "_last", {"path": None, "code": None, "what": None})
    code = cad.design("phone stand")
    assert code.startswith("// Phone stand") and asked and asked[0]["model"] == config.LLM_MODEL


def test_part_named_only_in_name_or_details(model, monkeypatch):
    """A model sent {'name': 'arduino_case', 'details': ...} with no 'what'; that's still a part."""
    monkeypatch.setattr(cad, "_exe", lambda: None)
    out = cad.make_3d_model({"name": "arduino_case", "details": "with USB cutout"})
    assert "Say what part to make" not in out
    assert "arduino case" in model[0][1]
    assert "Say what part to make" in cad.make_3d_model({})
