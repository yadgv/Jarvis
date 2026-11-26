"""Jarvis's own 3D viewer: shows the parts he designs in a holographic window.

OpenSCAD still builds the part (in the background, no window); the STL it
makes is shown here instead of in OpenSCAD's own (dated) window. Drag to
rotate, right-drag to pan, scroll to zoom. The page draws it with WebGL in an
Edge/Chrome app window, so nothing new needs installing. "Open in OpenSCAD"
is a button on it (and a voice request) for editing the code by hand.
"""
import http.server
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

import config

TITLE = "Jarvis 3D viewer"
PAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer3d.html")
GONE_AFTER = 8.0      # the page asks every second; quiet this long = window closed

_lock = threading.Lock()
_part = {"version": 0, "name": "", "stl": "", "scad": ""}
_server = None
_opened = False
_launched = 0.0
_last_seen = 0.0
_said_bye = 0.0


def info() -> dict:
    with _lock:
        p = dict(_part)
    return {"version": p["version"], "name": p["name"],
            "has_model": bool(p["stl"] and os.path.exists(p["stl"])),
            "openscad": bool(p["scad"] and os.path.exists(p["scad"]))}


def _openscad(scad: str) -> str:
    from skills import cad
    if not scad or not os.path.exists(scad):
        return "There's no part file to open yet."
    exe = cad._exe()
    if not exe:
        return "OpenSCAD isn't installed (it's free at openscad.org)."
    try:
        subprocess.Popen([cad._gui(exe), scad], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return f"Couldn't open OpenSCAD: {e}"
    return "Opened in OpenSCAD."


def _show_file(path: str) -> str:
    if not path or not os.path.exists(path):
        return "There's no file yet."
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError as e:
        return f"Couldn't open the folder: {e}"
    return "Opened the folder."


class _Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body, kind, code=200):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        global _last_seen
        path = self.path.partition("?")[0]
        if path == "/":
            with open(PAGE_FILE, "rb") as f:
                self._send(f.read(), "text/html; charset=utf-8")
        elif path == "/info.json":
            _last_seen = time.monotonic()
            self._send(json.dumps(info()), "application/json")
        elif path == "/model.stl":
            with _lock:
                stl = _part["stl"]
            try:
                with open(stl, "rb") as f:
                    self._send(f.read(), "model/stl")
            except OSError:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        global _said_bye
        path = self.path.partition("?")[0]
        with _lock:
            part = dict(_part)
        if path == "/bye":
            _said_bye = time.monotonic()
            self._send("{}", "application/json")
        elif path == "/openscad":
            self._send(json.dumps({"message": _openscad(part["scad"]).upper()}), "application/json")
        elif path == "/folder":
            self._send(json.dumps({"message": _show_file(part["stl"] or part["scad"]).upper()}),
                       "application/json")
        else:
            self.send_error(404)

    def log_message(self, *a):  # keep jarvis.log clean
        pass


def url() -> str:
    global _server
    if _server is None:
        _server = http.server.ThreadingHTTPServer(("127.0.0.1", getattr(config, "VIEWER_PORT", 0)), _Handler)
        threading.Thread(target=_server.serve_forever, daemon=True, name="viewer3d").start()
    return f"http://127.0.0.1:{_server.server_address[1]}/"


def window_open() -> bool:
    if not _opened or _said_bye > max(_last_seen, _launched):
        return False
    if _last_seen >= _launched:
        return time.monotonic() - _last_seen < GONE_AFTER
    return time.monotonic() - _launched < 10


def _to_front(wait: float = 15.0):
    """Windows: pin the viewer on top (like the whiteboard) once it has opened."""
    if sys.platform != "win32":
        return

    def run():
        from skills import whiteboard
        try:
            user32 = whiteboard._user32()
            end = time.monotonic() + wait
            while time.monotonic() < end:
                hwnd = whiteboard._find_window(user32, TITLE)
                if hwnd:
                    whiteboard._raise(user32, hwnd, pin=True)
                    return
                time.sleep(0.25)
        except Exception as e:
            print(f"[3d viewer] couldn't bring the window to the front: {e}")

    threading.Thread(target=run, daemon=True, name="viewer3d-front").start()


def open_window():
    global _opened, _launched
    if window_open():
        _to_front(wait=3)   # the page picks up the new part by itself
        return
    from skills import whiteboard
    _opened, _launched = True, time.monotonic()
    link = url()
    exe = whiteboard._app_browser()
    try:
        if exe:
            subprocess.Popen([exe, f"--app={link}", "--window-size=1180,820"])
            _to_front()
            return
    except Exception as e:
        print(f"[3d viewer] couldn't open an app window ({e}); using the browser")
    webbrowser.open(link)


def show(stl: str, name: str = "", scad: str = "") -> None:
    """Put a part in the viewer and open it (or bring it to the front)."""
    with _lock:
        _part.update(stl=stl, scad=scad, name=name or os.path.splitext(os.path.basename(stl))[0],
                     version=_part["version"] + 1)
    open_window()


# ---------- tools ----------

def show_3d_model(a=None):
    with _lock:
        stl = _part["stl"]
    if not stl:
        from skills import cad
        last = cad._last.get("path") or ""
        stl = os.path.splitext(last)[0] + ".stl" if last else ""
        if stl and os.path.exists(stl):
            show(stl, scad=last)
            return "The last part is in the 3D viewer."
        return "There's no 3D part yet. Offer to design one."
    open_window()
    return "The 3D viewer is open."


def open_in_openscad(a=None):
    from skills import cad
    with _lock:
        scad = _part["scad"]
    return _openscad(scad or cad._last.get("path") or "")


SKILLS = [
    {
        "name": "show_3d_model",
        "description": "Show the last 3D part again in Jarvis's 3D viewer ('show me the part', 'open the 3D model').",
        "parameters": {"type": "object", "properties": {}},
        "run": show_3d_model,
    },
    {
        "name": "open_in_openscad",
        "description": "Open the last 3D part's code in OpenSCAD itself, to edit it by hand ('open it in OpenSCAD').",
        "parameters": {"type": "object", "properties": {}},
        "run": open_in_openscad,
    },
]
