"""The whiteboard: Jarvis draws a diagram and talks you through it step by step.

"Show me how to wire a servo to my Arduino" opens a window with a labelled
drawing (board, pins, wires, parts). Each step lights up its own wires while
he explains it; say "next step", "go back" or "step 3" (or click), and ask for
changes ("use pin 6 instead") to redraw it. Works for circuits, flowcharts,
how things connect, and so on.

Idea from Clicky (github.com/farzaa/clicky), which draws on a canvas while it
explains. Here a big free model on Groq (WHITEBOARD_MODELS in config.py) only
describes the parts, pins and wires as JSON, and skills/diagram.py draws them
from accurate templates (a real Arduino Uno layout, part cards, wires on their
own lanes); Claude only if the free ones fail. The page is served on
this PC only (127.0.0.1) and shown in an app window (Edge/Chrome) or the browser.
"""
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser

import config

MAX_TOKENS = 3000
PART_TYPES = "arduino_uno, servo, led, resistor, button, potentiometer, buzzer, sensor, ultrasonic, motor, relay, lcd_i2c, battery, generic"
SYSTEM = (
    "You plan teaching diagrams for a whiteboard. You don't draw: you describe the parts and connections "
    "as JSON, and the whiteboard draws them neatly. Reply with ONLY one JSON object, no other text.\n\n"
    "For wiring something up:\n"
    '{"title": "Servo on an Arduino Uno", "kind": "wiring",\n'
    ' "parts": [{"id": "uno", "type": "arduino_uno"}, {"id": "servo", "type": "servo", "label": "SG90 servo"},\n'
    '           {"id": "r1", "type": "resistor", "value": "220 ohm"}],\n'
    ' "wires": [{"from": "uno.5V", "to": "servo.V+", "step": 1},\n'
    '           {"from": "uno.GND", "to": "servo.GND", "step": 2},\n'
    '           {"from": "uno.D9", "to": "servo.SIG", "step": 3, "label": "signal"}],\n'
    ' "steps": ["Red wire: Arduino 5V to the servo\'s power lead.", "...", "..."]}\n\n'
    "For anything else (a process, an idea, how something works) use a flowchart:\n"
    '{"title": "...", "kind": "flowchart",\n'
    ' "nodes": [{"id": "a", "text": "Read the sensor", "shape": "start|box|decision|end"}, ...],\n'
    ' "edges": [{"from": "a", "to": "b", "label": "yes", "step": 1}, ...], "steps": ["...", "..."]}\n\n'
    "Rules:\n"
    f"- Part types: {PART_TYPES}. A part with other pins can list them: \"pins\": [\"VCC\", \"DATA\", \"GND\"].\n"
    "- Arduino Uno pins are named exactly: 5V, 3.3V, VIN, GND, D0-D13, A0-A5, AREF, SDA, SCL. "
    "Servo pins: GND, V+, SIG. LED pins: + (long leg), - (short leg). Resistor and button pins: 1, 2.\n"
    "- Wire ends are \"partid.PIN\". Connect parts directly (no breadboard). Put a resistor in series "
    "with every LED. Each wire has the step number it's connected in; steps count from 1.\n"
    "- steps: 3 to 8 short, plain spoken sentences, one per step number, in the order he should do them, "
    "naming the pins. Warn if something needs outside power.\n"
    "- Labels are short (2-3 words). Be correct."
)
_JSON = re.compile(r"\{.*\}", re.DOTALL)

# What's on the board now (also what the page polls).
_board = {"version": 0, "title": "", "svg": "", "steps": [], "step": 0, "topic": "", "spec": None}
_lock = threading.Lock()
_server = None
_opened = False


# ---------- making the drawing ----------

def parse(text: str) -> dict:
    """The model's JSON -> {"title", "spec", "svg", "steps", "skipped"}. Raises ValueError if unusable."""
    from skills import diagram
    m = _JSON.search(re.sub(r"```(?:json)?", "", text or ""))
    if not m:
        raise ValueError("the model didn't describe a diagram")
    try:
        spec = json.loads(m.group(0))
    except ValueError as e:
        raise ValueError(f"the description wasn't valid JSON ({e})")
    if not isinstance(spec, dict) or not (spec.get("wires") or spec.get("nodes")):
        raise ValueError("the description had nothing to draw")
    svg, skipped = diagram.render(spec)
    steps = [str(s).strip() for s in spec.get("steps") or [] if str(s).strip()][:12]
    if skipped:
        print(f"[whiteboard] couldn't draw: {', '.join(skipped)}")
    return {"title": str(spec.get("title") or "Whiteboard")[:80], "spec": spec, "svg": svg,
            "steps": steps, "skipped": skipped}


def draw(topic: str, change: str = "") -> dict:
    from brain import llm
    if change and _board.get("spec"):
        prompt = (f"Here is the current whiteboard for: {_board['topic']}\n{json.dumps(_board['spec'])}\n\n"
                  f"Change it like this, and send the whole new JSON: {change}")
    else:
        prompt = f"Plan a whiteboard diagram, step by step, for: {topic}"
    text = llm.complete(SYSTEM, prompt, max_tokens=MAX_TOKENS, small=False,
                        models=getattr(config, "WHITEBOARD_MODELS", None))
    return parse(text)


# ---------- the page ----------

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Jarvis whiteboard</title>
<style>
body{margin:0;background:#eef1f6;color:#1d2433;font-family:Segoe UI,system-ui,sans-serif;display:flex;height:100vh;overflow:hidden}
#board svg{font-variant-ligatures:none}
#board{flex:1;position:relative;background:#ffffff;margin:12px;border-radius:14px;box-shadow:0 2px 12px #0002;overflow:hidden;cursor:grab}
#board.drag{cursor:grabbing}#board svg{width:100%;height:100%;display:block}
#zoom{position:absolute;right:14px;bottom:14px;display:flex;gap:6px}
#zoom button{width:44px;font-size:20px;padding:6px 0}
#side{width:340px;background:#ffffff;padding:22px;overflow:auto;box-shadow:-2px 0 12px #0001}
h1{font-size:24px;margin:0 0 16px}
ol{padding-left:24px;margin:0}li{margin:0 0 14px;line-height:1.45;font-size:18px;color:#7b8494;cursor:pointer}
li.on{color:#1d2433;font-weight:700;background:#fff3bf;border-radius:8px;padding:6px 8px;margin-left:-8px}li.done{color:#495057}
#nav{margin-top:18px;display:flex;gap:8px}button{flex:1;background:#1c7ed6;color:#fff;border:0;
border-radius:10px;padding:10px;font-size:16px;cursor:pointer}button:hover{background:#1971c2}
button.alt{background:#e9ecef;color:#1d2433}button.alt:hover{background:#dee2e6}
g[id^="step-"]{transition:opacity .35s}
g[id^="step-"].later{opacity:.08}g[id^="step-"].past{opacity:.45}
g[id^="step-"].now .wire{stroke-width:9}
g[id^="step-"].now{filter:drop-shadow(0 0 5px #ffd43b) drop-shadow(0 0 10px #fab005)}
.hint{margin-top:16px;font-size:14px;color:#7b8494;line-height:1.4}
</style></head>
<body><div id="board"><div id="zoom"><button class="alt" id="zin">+</button><button class="alt" id="zout">&minus;</button>
<button class="alt" id="fit" style="width:60px;font-size:15px">Fit</button></div></div>
<div id="side"><h1 id="title">Whiteboard</h1><ol id="steps"></ol>
<div id="nav"><button class="alt" id="back">&#8592; Back</button><button class="alt" id="all">All</button><button id="next">Next &#8594;</button></div>
<div class="hint">Say "next step", "go back" or "step 3".<br>Scroll to zoom, drag to move, Fit to see it all.</div></div>
<script src="/app.js"></script></body></html>"""

APP_JS = """
let version = -1, step = -1, svg = null, home = null, view = null;
async function poll() {
  try {
    const b = await (await fetch('/board.json', {cache: 'no-store'})).json();
    if (b.version !== version) {
      version = b.version;
      document.title = b.title || 'Jarvis whiteboard';
      document.getElementById('title').textContent = b.title || 'Whiteboard';
      const doc = new DOMParser().parseFromString(b.svg || '<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/svg+xml');
      const board = document.getElementById('board');
      if (svg) svg.remove();
      svg = document.importNode(doc.documentElement, true);
      board.insertBefore(svg, board.firstChild);
      home = (svg.getAttribute('viewBox') || '0 0 1000 700').split(/\\s+/).map(Number);
      view = home.slice(); setView();
      const ol = document.getElementById('steps');
      ol.replaceChildren(...(b.steps || []).map((s, i) => {
        const li = document.createElement('li'); li.textContent = s;
        li.onclick = () => go(i + 1); return li; }));
      step = -1;
    }
    if (b.step !== step) { step = b.step; show(step); }
  } catch (e) {}
  setTimeout(poll, 400);
}
function setView() { if (svg) svg.setAttribute('viewBox', view.join(' ')); }
function zoom(f, cx, cy) {
  if (!view) return;
  const r = svg.getBoundingClientRect();
  const px = cx === undefined ? 0.5 : (cx - r.left) / r.width, py = cy === undefined ? 0.5 : (cy - r.top) / r.height;
  const w = Math.min(home[2] * 3, Math.max(home[2] / 6, view[2] * f)), h = w * view[3] / view[2];
  view = [view[0] + (view[2] - w) * px, view[1] + (view[3] - h) * py, w, h]; setView();
}
const boardEl = document.getElementById('board');
boardEl.addEventListener('wheel', e => { e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); }, {passive: false});
let dragFrom = null;
boardEl.addEventListener('mousedown', e => { if (e.target.closest('#zoom')) return; dragFrom = [e.clientX, e.clientY]; boardEl.classList.add('drag'); });
window.addEventListener('mouseup', () => { dragFrom = null; boardEl.classList.remove('drag'); });
window.addEventListener('mousemove', e => {
  if (!dragFrom || !view) return;
  const r = svg.getBoundingClientRect(), s = Math.max(view[2] / r.width, view[3] / r.height);
  view[0] -= (e.clientX - dragFrom[0]) * s; view[1] -= (e.clientY - dragFrom[1]) * s;
  dragFrom = [e.clientX, e.clientY]; setView();
});
document.getElementById('zin').onclick = () => zoom(1 / 1.25);
document.getElementById('zout').onclick = () => zoom(1.25);
document.getElementById('fit').onclick = () => { if (home) { view = home.slice(); setView(); } };
function show(n) {
  document.querySelectorAll('g[id^="step-"]').forEach(g => {
    const k = parseInt(g.id.slice(5));
    g.classList.remove('now', 'past', 'later');
    if (n > 0) g.classList.add(k === n ? 'now' : (k < n ? 'past' : 'later'));
  });
  document.querySelectorAll('#steps li').forEach((li, i) => {
    li.className = (i + 1 === n) ? 'on' : (n > 0 && i + 1 < n ? 'done' : '');
  });
}
function go(n) { fetch('/step?n=' + n, {cache: 'no-store'}); }
document.getElementById('next').onclick = () => go(step + 1);
document.getElementById('back').onclick = () => go(Math.max(1, step - 1));
document.getElementById('all').onclick = () => go(0);
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight' || e.key === ' ') go(step + 1);
  if (e.key === 'ArrowLeft') go(Math.max(1, step - 1));
  if (e.key === '+' || e.key === '=') zoom(1 / 1.25);
  if (e.key === '-') zoom(1.25);
  if (e.key === '0') { view = home.slice(); setView(); }
});
poll();
"""

# The page may only run our own script, never anything inside the drawing.
CSP = "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; img-src data:"


def set_step(n: int) -> int:
    with _lock:
        total = len(_board["steps"])
        _board["step"] = max(0, min(int(n), total))
        return _board["step"]


class _Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body: str, kind: str):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/":
            self._send(PAGE, "text/html")
        elif path == "/app.js":
            self._send(APP_JS, "application/javascript")
        elif path == "/board.json":
            with _lock:
                self._send(json.dumps({k: _board[k] for k in ("version", "title", "svg", "steps", "step")}),
                           "application/json")
        elif path == "/step":
            m = re.search(r"(?:^|&)n=(-?\d+)", query)
            set_step(int(m.group(1)) if m else 0)
            self._send("{}", "application/json")
        else:
            self.send_error(404)

    def log_message(self, *a):  # keep jarvis.log clean
        pass


def url() -> str:
    global _server
    if _server is None:
        _server = http.server.ThreadingHTTPServer(("127.0.0.1", getattr(config, "WHITEBOARD_PORT", 0)), _Handler)
        threading.Thread(target=_server.serve_forever, daemon=True, name="whiteboard").start()
    return f"http://127.0.0.1:{_server.server_address[1]}/"


def _app_browser():
    """Edge or Chrome, to open the page as its own window with no tabs or address bar."""
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
            for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
                if base and os.path.exists(os.path.join(base, rel)):
                    return os.path.join(base, rel)
        return None
    return shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")


def open_window():
    global _opened
    if _opened:
        return
    _opened = True
    link = url()
    exe = _app_browser()
    try:
        if exe:
            subprocess.Popen([exe, f"--app={link}", "--start-maximized"])  # big = readable
            return
    except Exception as e:
        print(f"[whiteboard] couldn't open an app window ({e}); using the browser")
    webbrowser.open(link)


# ---------- tools ----------

def _summary(intro: str) -> str:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(_board["steps"], 1))
    return (f"{intro} \"{_board['title']}\", step 1 is lit up. Steps:\n{steps}\n"
            "Say one short line that it's on the whiteboard, then explain step 1 only, briefly. "
            "He moves on with 'next step' (whiteboard_step).")


def show_diagram(a):
    topic = (a.get("topic") or "").strip()
    change = (a.get("change") or "").strip()
    if not topic and not change:
        return "Say what to draw."
    try:
        board = draw(topic or _board["topic"], change)
    except ValueError as e:
        return f"Couldn't draw it: {e}. Offer to try again."
    with _lock:
        _board.update(board, topic=topic or _board["topic"], step=1 if board["steps"] else 0,
                      version=_board["version"] + 1)
    open_window()
    return _summary("Redrawn:" if change else "On the whiteboard:")


def whiteboard_step(a):
    if not _board["svg"]:
        return "The whiteboard is empty. Use show_diagram first."
    action = (a.get("action") or "next").lower()
    if action == "goto":
        n = set_step(a.get("step") or 1)
    elif action == "back":
        n = set_step(max(1, _board["step"] - 1))
    elif action == "all":
        n = set_step(0)
    else:
        if _board["step"] >= len(_board["steps"]):
            return "That was the last step. Ask if he has questions, or wants anything changed."
        n = set_step(_board["step"] + 1)
    open_window()
    if n == 0:
        return "Showing the whole drawing."
    return f"Step {n} of {len(_board['steps'])} is lit up: {_board['steps'][n - 1]} Explain just this step, briefly."


SKILLS = [
    {
        "name": "show_diagram",
        "description": (
            "Draw a diagram on the whiteboard window and walk him through it step by step: how to wire "
            "something to his Arduino or breadboard, a circuit, a flowchart, how parts connect. Use when he "
            "says 'show me', 'draw', 'visualize' or 'how do I wire/connect'. To change the current drawing "
            "('use pin 6 instead', 'add an LED'), pass change."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "what to draw, with any parts and pins he mentioned"},
                "change": {"type": "string", "description": "a change to the drawing already on the whiteboard"},
            },
        },
        "run": show_diagram,
    },
    {
        "name": "whiteboard_step",
        "description": "Move through the whiteboard's steps: 'next step', 'go back', 'step 3', 'show it all'.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["next", "back", "goto", "all"]},
                "step": {"type": "integer", "description": "for goto"},
            },
            "required": ["action"],
        },
        "run": whiteboard_step,
    },
]
