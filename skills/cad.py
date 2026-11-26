"""3D printable parts: "Jarvis, make me a phone stand" writes an OpenSCAD file.

A big free model on Groq (WHITEBOARD_MODELS) writes OpenSCAD code for the
part, in millimetres, with the sizes as named variables at the top so they're
easy to tweak. Jarvis saves it in Documents/Jarvis 3D, and if OpenSCAD is
installed (openscad.org, free) he also exports an STL ready for the slicer,
puts a preview picture on the whiteboard, and opens the file in OpenSCAD.
"Make it 10 mm taller" changes the last part.
"""
import base64
import os
import re
import shutil
import subprocess
import tempfile

import config

MAX_TOKENS = 3000
FOLDER_NAME = "Jarvis 3D"
SYSTEM = (
    "You design parts for 3D printing in OpenSCAD. Reply with ONLY OpenSCAD code, no other text.\n"
    "- Units are millimetres. Put every size as a named variable at the top with a short comment, "
    "e.g. `width = 80; // phone width + 2 mm clearance`.\n"
    "- First line: a comment with the part name. Use $fn = 64 for round things.\n"
    "- Make one solid, printable part that sits flat on the bed (z = 0 at the bottom), with no overhangs "
    "steeper than 45 degrees where you can avoid them, walls at least 1.6 mm, and 0.2-0.4 mm clearance "
    "for parts that fit together.\n"
    "- Use only built-in OpenSCAD: cube, cylinder, sphere, polygon, linear_extrude, rotate_extrude, "
    "translate, rotate, scale, mirror, hull, minkowski, union, difference, intersection, modules, for. "
    "No include, use, import or surface. There are no libraries: rounded_cube, cuboid and the like don't "
    "exist, so write any helper module yourself before using it. End every statement with ;."
)
_BANNED = re.compile(r"^\s*(?:include|use)\s*<|\b(?:import|surface)\s*\(", re.M)

_last = {"path": None, "code": None, "what": None}


def _console(path):
    """On Windows openscad.exe is the window app: it prints no errors where
    Jarvis can read them. openscad.com, next to it, is the same program for
    the command line, so use that when it's there."""
    if path and path.lower().endswith(".exe"):
        for name in ("openscad.com", "openscad.console.exe"):
            other = os.path.join(os.path.dirname(path), name)
            if os.path.isfile(other):
                return other
    return path


def _exe():
    """The OpenSCAD program for the command line, or None."""
    found = shutil.which("openscad.com") or shutil.which("openscad")
    if found:
        return _console(found)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramW6432", "")):
        for sub in ("OpenSCAD", os.path.join("Programs", "OpenSCAD"), "OpenSCAD (Nightly)", "OpenSCAD (Nightly) "):
            for exe in ("openscad.com", "openscad.console.exe", "openscad.exe"):
                path = os.path.join(base or "", sub, exe)
                if base and os.path.isfile(path):
                    return path
    return None


def _gui(exe):
    """The window app, for opening the file for him."""
    for name in ("openscad.exe",):
        other = os.path.join(os.path.dirname(exe), name)
        if os.path.isfile(other):
            return other
    return exe


def clean(text: str) -> str:
    """The model's reply -> OpenSCAD code. Raises ValueError if it isn't usable."""
    text = text or ""
    m = re.search(r"```(?:openscad|scad)?\s*\n(.*?)```", text, re.S)
    code = (m.group(1) if m else text).strip()
    if not code or not re.search(r"\b(?:cube|cylinder|sphere|polygon|linear_extrude|rotate_extrude|polyhedron)\s*\(", code):
        raise ValueError("the model didn't write a shape")
    if _BANNED.search(code):
        raise ValueError("the code tried to read other files")
    if code.count("{") != code.count("}") or code.count("(") != code.count(")"):
        raise ValueError("the code was cut off")
    return code + "\n"


def design(what: str, details: str = "", change: str = "") -> str:
    from brain import llm
    if change and _last["code"]:
        prompt = f"Here is the OpenSCAD for {_last['what']}:\n{_last['code']}\nChange it like this and send all the code: {change}"
    else:
        prompt = f"Design this part: {what}." + (f" Details: {details}" if details else "")
    # A model that answers with chat instead of code is skipped for the next
    # one, and Claude (Haiku) writes it if none of the free ones can.
    return clean(llm.complete(SYSTEM, prompt, max_tokens=MAX_TOKENS, small=False,
                              models=getattr(config, "WHITEBOARD_MODELS", None), check=clean))


def _render(exe, scad, out, extra=()):
    """Run OpenSCAD; '' if it worked, else why not. Everything goes in the log."""
    cmd = [exe, "-o", out, *extra, scad]
    try:
        if os.path.exists(out):
            os.remove(out)
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[3d] {subprocess.list2cmdline(cmd)} -> couldn't run: {e}")
        return f"couldn't run OpenSCAD ({e})"
    text = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
    made = os.path.exists(out) and os.path.getsize(out) > 0
    print(f"[3d] {subprocess.list2cmdline(cmd)} -> exit {r.returncode}, "
          f"{'made the file' if made else 'NO FILE'}" + (f"\n[3d] OpenSCAD said:\n{text[-1500:]}" if text else ", no output"))
    lines = text.splitlines()
    # Mistakes OpenSCAD only warns about leave parts out of the model (a made-up
    # module like rounded_cube() draws nothing), so they count as errors too.
    errors = [l.strip() for l in lines if "ERROR" in l or ("WARNING" in l and any(
        w in l.lower() for w in ("unknown", "undefined", "child modules", "wrong number", "too many")))]
    if made and r.returncode == 0 and not errors:
        return ""
    if errors:
        return "; ".join(errors[:2])[:400]
    empty = [l.strip() for l in lines if "top level" in l.lower() or "empty" in l.lower() or "not a 3d" in l.lower()]
    if empty:
        return empty[0][:300]
    if not text and exe.lower().endswith(".exe"):
        return ("OpenSCAD ran but printed nothing (this is its window app; openscad.com next to it shows errors). "
                f"Exit code {r.returncode}")
    return (lines[-1].strip()[:300] if lines else f"no file was made (exit code {r.returncode})")


def _preview(exe, scad, title):
    """A picture of the part on the whiteboard."""
    from skills import whiteboard
    png = os.path.join(tempfile.gettempdir(), "jarvis_part_preview.png")
    if _render(exe, scad, png, ["--imgsize=1200,900", "--viewall", "--autocenter", "--colorscheme=Tomorrow"]):
        return False
    with open(png, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    svg = (f'<svg viewBox="0 0 1200 900" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#fff"/>'
           f'<image href="data:image/png;base64,{data}" x="0" y="0" width="1200" height="900"/></svg>')
    whiteboard.show_svg(title, svg, [], title)
    return True


def make_3d_model(a):
    from skills import files
    what = (a.get("what") or "").strip()
    change = (a.get("change") or "").strip()
    if change and not _last["code"]:
        return "There's no part to change yet. Ask what to make."
    if not what and not change:
        return "Say what part to make."
    try:
        code = design(what or _last["what"], a.get("details") or "", change)
    except ValueError as e:
        return f"Couldn't design it: {e}. Offer to try again."
    except Exception as e:
        return f"Couldn't design it: {type(e).__name__}: {e}"
    folder = os.path.join(files._folder("documents") or os.path.expanduser("~"), FOLDER_NAME)
    os.makedirs(folder, exist_ok=True)
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", a.get("name") or what or _last["what"] or "part")
    stem = re.sub(r"\s+", " ", stem).strip()[:60] or "part"
    scad = files._unique(os.path.join(folder, stem + ".scad"))
    with open(scad, "w", encoding="utf-8") as f:
        f.write(code)
    made = [("", scad)]
    _last.update(path=scad, code=code, what=what or _last["what"])
    sizes = re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*([-\d.]+)\s*;", code, re.M | re.I)[:6]
    knobs = ", ".join(f"{k} {v} mm" for k, v in sizes)
    exe = _exe()
    if not exe:
        files._log("make", made)
        return (f"Saved {files._show(scad)}. OpenSCAD isn't installed, so I couldn't preview it or make the STL. "
                f"Sizes: {knobs}. Tell him it's saved and that OpenSCAD (free, openscad.org) opens it and exports "
                "the STL for his printer.")
    out = []
    if a.get("stl", True):
        stl = os.path.splitext(scad)[0] + ".stl"
        err = _render(exe, scad, stl)
        if err and "couldn't run" not in err and "printed nothing" not in err:
            # Usually a mistake in the code: let the model fix it once.
            print(f"[3d] build failed ({err}); asking the model to fix it")
            try:
                code = design(_last["what"], "", f"OpenSCAD gave this error, fix it: {err}")
                with open(scad, "w", encoding="utf-8") as f:
                    f.write(code)
                _last.update(code=code)
                err = _render(exe, scad, stl)
            except Exception as e:
                print(f"[3d] the fix didn't work: {e}")
        if err:
            files._log("make", made)
            return (f"Saved {files._show(scad)}, but OpenSCAD couldn't build it: {err}. The full error is in "
                    "the log. Tell him briefly and offer to try again (make_3d_model with change: 'fix: ...').")
        made.append(("", stl))
        out.append(f"the STL for the slicer is {files._show(stl)}")
    files._log("make", made)
    stl = os.path.splitext(scad)[0] + ".stl"
    if os.path.exists(stl):
        from skills import viewer3d
        try:
            viewer3d.show(stl, stem, scad)   # Jarvis's own viewer: drag to turn it, scroll to zoom
            out.append("it's in the 3D viewer (drag to turn it)")
        except Exception as e:
            print(f"[3d] viewer: {e}")
            if _preview(exe, scad, stem):
                out.append("a preview is on the whiteboard")
    elif _preview(exe, scad, stem):
        out.append("a preview is on the whiteboard")
    if a.get("open"):
        try:
            subprocess.Popen([_gui(exe), scad], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            out.append("it's open in OpenSCAD")
        except OSError:
            pass
    return (f"Saved {files._show(scad)}; " + "; ".join(out) + f". Sizes: {knobs}. Tell him briefly; he can ask "
            "to change any size, or say \"undo that\" to bin the files.")


SKILLS = [
    {
        "name": "make_3d_model",
        "description": ("Design a 3D printable part ('make me a phone stand', 'a 30 mm box with a lid', 'a bracket "
                        "for my servo'): writes an OpenSCAD file in Documents/Jarvis 3D, exports the STL and shows "
                        "it in Jarvis's 3D viewer if OpenSCAD is installed. To change the last part ('make it 10 mm taller') "
                        "pass change."),
        "parameters": {"type": "object", "properties": {
            "what": {"type": "string", "description": "the part, with any sizes he gave"},
            "details": {"type": "string", "description": "fit, sizes in mm, what it holds, printer limits"},
            "change": {"type": "string", "description": "a change to the last part"},
            "name": {"type": "string", "description": "file name without extension"},
            "stl": {"type": "boolean", "description": "also export an STL (default true)"},
            "open": {"type": "boolean", "description": "also open OpenSCAD's own window: ONLY if he explicitly asked for OpenSCAD (default false)"}}},
        "run": make_3d_model,
    },
]
