"""The whiteboard: Jarvis draws a diagram and talks you through it step by step.

"Show me how to wire a servo to my Arduino" opens a window with a labelled
drawing (board, pins, wires, parts). Each step lights up its own wires while
he explains it; say "next step", "go back" or "step 3" (or click), and ask for
changes ("use pin 6 instead") to redraw it. Works for circuits, flowcharts,
how things connect, and so on.

Idea from Clicky (github.com/farzaa/clicky), which draws on a canvas while it
explains. Here a big free model on Groq (WHITEBOARD_MODELS in config.py) writes
the drawing as SVG; Claude only if the free ones fail. The page is served on
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

MAX_TOKENS = 3500
SYSTEM = (
    "You draw clear teaching diagrams for a whiteboard, as SVG, and split the explanation into steps.\n"
    "Answer in exactly this format and nothing else:\n"
    "TITLE: <short title>\n"
    "<svg viewBox=\"0 0 1000 640\" xmlns=\"http://www.w3.org/2000/svg\"> ... </svg>\n"
    "STEP 1: <one or two plain spoken sentences>\n"
    "STEP 2: ...\n\n"
    "Drawing rules:\n"
    "- The background is dark navy; draw with light colours. Text: fill #e8eef7, font-family sans-serif, "
    "font-size 16 or more. Keep everything inside the viewBox with margins, and don't let labels overlap.\n"
    "- Draw real parts as labelled shapes: e.g. an Arduino Uno as a teal rectangle with its header pins as "
    "small labelled squares (5V, 3.3V, GND, A0-A5, D2-D13; ~ marks PWM pins), breadboards, resistors, LEDs, "
    "servos with their 3 leads, sensors with labelled pins. For flowcharts use boxes and arrows.\n"
    "- Wires are thick lines or paths (stroke-width 5, stroke-linecap round) in the usual colours: "
    "red #ff5a5a for power, grey #9aa4b2 for ground, yellow #ffd23f or orange #ff9f1c for signals.\n"
    "- Put the parts that are always there in <g id=\"base\">. Put everything added or connected in step N "
    "in <g id=\"step-N\"> (a wire plus its small label), so each step can be highlighted.\n"
    "- 3 to 8 steps, in the order he should do them; each step says what to connect to what, by pin name.\n"
    "- Only plain SVG shapes and text: no scripts, no images, no foreignObject, no links, no CSS imports.\n"
    "- Be correct: real pin names, and warn in a step if something needs a resistor or outside power."
)

# What's on the board now (also what the page polls).
_board = {"version": 0, "title": "", "svg": "", "steps": [], "step": 0, "topic": ""}
_lock = threading.Lock()
_server = None
_opened = False


# ---------- making the drawing ----------

_BAD = r"(?:script|foreignObject|iframe|object|embed|image|use|a|link|meta)"
_BAD_PAIR = re.compile(r"<\s*(" + _BAD + r")\b[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_BAD_TAG = re.compile(r"<\s*/?\s*" + _BAD + r"\b[^>]*>", re.IGNORECASE)
_BAD_ATTRS = re.compile(r"\s(?:on[a-z]+|href|xlink:href|src)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
                        re.IGNORECASE)


def clean_svg(svg: str) -> str:
    """Keep only plain drawing: the model's SVG never gets to run anything
    (the page's security policy blocks scripts and outside links as well)."""
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.DOTALL)
    prev = None
    while prev != svg:
        prev = svg
        svg = _BAD_TAG.sub("", _BAD_PAIR.sub("", svg))
    svg = _BAD_ATTRS.sub("", svg)
    return re.sub(r"javascript:|@import", "", svg, flags=re.IGNORECASE)


def parse(text: str) -> dict:
    """The model's answer -> {"title", "svg", "steps"}. Raises ValueError if there's no drawing."""
    text = re.sub(r"```(?:svg|xml|html)?", "", text or "")
    m = re.search(r"<svg\b.*?</svg>", text, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("the model didn't send a drawing")
    title = re.search(r"^\s*TITLE:\s*(.+)$", text, re.MULTILINE)
    steps = re.findall(r"^\s*STEP\s*\d+\s*[:.)-]\s*(.+)$", text[m.end():], re.MULTILINE)
    return {"title": (title.group(1).strip() if title else "Whiteboard")[:80],
            "svg": clean_svg(m.group(0)),
            "steps": [s.strip() for s in steps][:12]}


def draw(topic: str, change: str = "") -> dict:
    from brain import llm
    if change and _board["svg"]:
        prompt = (f"Here is the current whiteboard for: {_board['topic']}\n\nTITLE: {_board['title']}\n"
                  f"{_board['svg']}\n" + "\n".join(f"STEP {i}: {s}" for i, s in enumerate(_board['steps'], 1))
                  + f"\n\nChange it like this, and send the whole new version: {change}")
    else:
        prompt = f"Draw this and explain it step by step: {topic}"
    text = llm.complete(SYSTEM, prompt, max_tokens=MAX_TOKENS, small=False,
                        models=getattr(config, "WHITEBOARD_MODELS", None))
    return parse(text)


# ---------- the page ----------

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Jarvis whiteboard</title>
<style>
body{margin:0;background:#0b1220;color:#e8eef7;font-family:Segoe UI,system-ui,sans-serif;display:flex;height:100vh}
#board{flex:1;display:flex;align-items:center;justify-content:center;padding:16px}
#board svg{width:100%;height:100%;max-height:calc(100vh - 32px)}
#board svg text:not([fill]){fill:#e8eef7}
#side{width:340px;background:#111a2e;padding:20px;overflow:auto;border-left:1px solid #22304d}
h1{font-size:20px;margin:0 0 14px}
ol{padding-left:22px;margin:0}li{margin:0 0 12px;line-height:1.4;color:#8da0bf;cursor:pointer}
li.on{color:#fff;font-weight:600}li.done{color:#c3cfe2}
#nav{margin-top:16px;display:flex;gap:8px}button{flex:1;background:#1d2b4a;color:#e8eef7;border:1px solid #33456e;
border-radius:8px;padding:8px;font-size:14px;cursor:pointer}button:hover{background:#26375c}
g[id^="step-"]{transition:opacity .35s,filter .35s}
g[id^="step-"].later{opacity:.12}g[id^="step-"].past{opacity:.55}
g[id^="step-"].now{opacity:1;filter:drop-shadow(0 0 6px #7fd3ff) drop-shadow(0 0 12px #3fa9ff)}
.hint{margin-top:14px;font-size:12px;color:#6b7c99}
</style></head>
<body><div id="board"></div><div id="side"><h1 id="title">Whiteboard</h1><ol id="steps"></ol>
<div id="nav"><button id="back">&#8592; Back</button><button id="all">All</button><button id="next">Next &#8594;</button></div>
<div class="hint">Or say "next step", "go back" or "step 3".</div></div>
<script src="/app.js"></script></body></html>"""

APP_JS = """
let version = -1, step = -1;
async function poll() {
  try {
    const b = await (await fetch('/board.json', {cache: 'no-store'})).json();
    if (b.version !== version) {
      version = b.version;
      document.title = b.title || 'Jarvis whiteboard';
      document.getElementById('title').textContent = b.title || 'Whiteboard';
      const doc = new DOMParser().parseFromString(b.svg || '<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/svg+xml');
      const board = document.getElementById('board');
      board.replaceChildren(document.importNode(doc.documentElement, true));
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
            subprocess.Popen([exe, f"--app={link}", "--window-size=1200,760"])
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
