"""Turns a structured description of a diagram into a clean, readable SVG.

The model never draws. It only says *what* is there:

    {"title": "...", "kind": "wiring",
     "parts": [{"id": "servo", "type": "servo", "label": "SG90 servo"}],
     "wires": [{"from": "uno.5V", "to": "servo.V+", "step": 1, "label": "power"}],
     "steps": ["Connect ...", ...]}

    {"title": "...", "kind": "flowchart",
     "nodes": [{"id": "start", "text": "Wake up", "shape": "start"}, ...],
     "edges": [{"from": "start", "to": "coffee", "label": "", "step": 1}],
     "steps": [...]}

and this file draws it the same tidy way every time: an Arduino Uno with its
real header layout, cards for the other parts with their pins, and wires that
leave each pin on their own lane so they never run on top of each other.
Wires are colour coded (red power, black ground, distinct colours for signals)
and labelled in big text. Everything a step adds is in <g id="step-N">, so the
whiteboard can light up one step at a time.
"""
import re
from html import escape

FONT = "Segoe UI, Arial, sans-serif"
INK = "#1d2433"
MUTED = "#5b6678"
POWER = "#e03131"
GROUND = "#111111"
SIGNALS = ["#f08c00", "#1c7ed6", "#2f9e44", "#9c36b5", "#0c8599", "#d6336c", "#5f3dc4", "#e8590c"]

# ---------- the Arduino Uno, with its real headers ----------
PIN = 30                       # spacing between header pins
UNO_W, UNO_H = 640, 380
# Top header, left to right as on the board (the gap between D8 and D7 is real).
UNO_TOP = ["SCL", "SDA", "AREF", "GND", "D13", "D12", "D11", "D10", "D9", "D8", None,
           "D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0"]
UNO_BOTTOM = ["IOREF", "RESET", "3.3V", "5V", "GND", "GND", "VIN", None, "A0", "A1", "A2", "A3", "A4", "A5"]
PWM = {"D3", "D5", "D6", "D9", "D10", "D11"}

# Pins each kind of part usually has (more are added if the wires use them).
PARTS = {
    "servo": {"pins": ["GND", "V+", "SIG"], "name": "Servo"},
    "led": {"pins": ["+", "-"], "name": "LED"},
    "resistor": {"pins": ["1", "2"], "name": "Resistor"},
    "button": {"pins": ["1", "2"], "name": "Push button"},
    "potentiometer": {"pins": ["VCC", "OUT", "GND"], "name": "Potentiometer"},
    "buzzer": {"pins": ["+", "-"], "name": "Buzzer"},
    "sensor": {"pins": ["VCC", "OUT", "GND"], "name": "Sensor"},
    "ultrasonic": {"pins": ["VCC", "TRIG", "ECHO", "GND"], "name": "Ultrasonic sensor"},
    "motor": {"pins": ["+", "-"], "name": "DC motor"},
    "relay": {"pins": ["VCC", "IN", "GND"], "name": "Relay module"},
    "lcd_i2c": {"pins": ["GND", "VCC", "SDA", "SCL"], "name": "I2C LCD"},
    "battery": {"pins": ["+", "-"], "name": "Battery"},
    "generic": {"pins": [], "name": "Part"},
}
_ALIASES = {"+": ["anode", "long leg", "positive", "vcc", "v+"], "-": ["cathode", "short leg", "negative", "gnd"],
            "V+": ["vcc", "5v", "power", "red", "+"], "SIG": ["signal", "pwm", "data", "orange", "yellow", "s"],
            "GND": ["ground", "brown", "black", "-", "0v"]}


def norm_uno_pin(name: str):
    """'pin 9', '~9', 'd9', 'digital 9' -> 'D9'; '5v' -> '5V'; unknown -> None."""
    p = re.sub(r"\s+", "", str(name).upper().replace("PIN", "").replace("DIGITAL", "").replace("~", ""))
    p = {"3V3": "3.3V", "3.3": "3.3V", "5": "5V", "GROUND": "GND", "VCC": "5V", "+5V": "5V"}.get(p, p)
    if re.fullmatch(r"\d{1,2}", p):
        p = "D" + p
    if re.fullmatch(r"ANALOG(\d)", p):
        p = "A" + p[-1]
    return p if p in UNO_TOP or p in UNO_BOTTOM else None


def wire_colour(a: str, b: str, index: int) -> str:
    """a, b: 'part.pin'. Black for ground, red for power, else the next signal colour."""
    pins = {e.split(".", 1)[1].upper() for e in (a, b)}
    if pins & {"GND", "-", "GROUND", "0V"}:
        return GROUND
    if pins & {"5V", "3.3V", "VIN", "VCC", "V+"}:
        return POWER
    return SIGNALS[index % len(SIGNALS)]


def plain(text) -> str:
    """Arrows and fancy dashes as plain text, so no font shows them as boxes."""
    from brain import textfix
    text = textfix.fix(text)
    for a, b in (("→", "->"), ("⟶", "->"), ("←", "<-"), ("↔", "<->"), ("—", "-"), ("–", "-"), ("Ω", " ohm")):
        text = text.replace(a, b)
    return text


def _t(x, y, text, size=18, anchor="start", weight="normal", fill=INK, extra=""):
    text = plain(text)
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" dominant-baseline="middle"{extra}>{escape(str(text))}</text>')


def _label(x, y, text, colour, size=21, right=False):
    """A wire label in a white pill, so it stays readable over anything.
    right=True: x is where the pill ends, not its middle."""
    text = plain(text)
    w = 18 + 0.58 * size * len(text)
    if right:
        x -= w / 2
    return (f'<rect x="{x - w / 2:.0f}" y="{y - 17:.0f}" width="{w:.0f}" height="34" rx="17" fill="#ffffff" '
            f'stroke="{colour}" stroke-width="2.5"/>' + _t(x, y + 1, text, size, "middle", "600"))


# ---------- wiring diagrams ----------

class _Layout:
    def __init__(self, spec):
        self.parts = [p for p in spec.get("parts", []) if isinstance(p, dict) and p.get("id")]
        self.wires = [w for w in spec.get("wires", []) if isinstance(w, dict) and w.get("from") and w.get("to")]
        self.has_uno = any(str(p.get("type", "")).lower() in ("arduino_uno", "arduino", "uno") for p in self.parts) \
            or any(str(w["from"]).split(".")[0].lower() in ("uno", "arduino") or
                   str(w["to"]).split(".")[0].lower() in ("uno", "arduino") for w in self.wires)
        self.uno_ids = {p["id"] for p in self.parts if str(p.get("type", "")).lower() in ("arduino_uno", "arduino", "uno")}
        self.uno_ids |= {"uno", "arduino"}
        self.cards = [p for p in self.parts if p["id"] not in self.uno_ids]
        self.pins = {}       # "part.pin" -> (x, y, side)
        self.used = set()
        self.skipped = []

    def _split(self, end: str):
        part, _, pin = str(end).partition(".")
        return part.strip(), pin.strip()

    def _card_pins(self, card):
        kind = PARTS.get(str(card.get("type", "")).lower(), PARTS["generic"])
        pins = [str(p) for p in (card.get("pins") or kind["pins"])]
        for w in self.wires:
            for end in (w["from"], w["to"]):
                part, pin = self._split(end)
                if part == card["id"] and pin and self._match(pins, pin) is None:
                    pins.append(pin)
        return pins

    @staticmethod
    def _match(pins, pin):
        low = pin.lower()
        for p in pins:
            if p.lower() == low:
                return p
        for p in pins:
            if low in _ALIASES.get(p, []):
                return p
        return None


def render_wiring(spec: dict) -> str:
    L = _Layout(spec)
    out_base, steps = [], {}
    n_wires = len(L.wires)
    lane_gap, chan_gap = 26, 24
    uno_x, uno_y = 60, 90 + chan_gap * n_wires
    lanes_x = (uno_x + UNO_W + 70) if L.has_uno else 120
    # Labels sit in their own strip between the last lane and the parts, so
    # they never cover a wire running up or down.
    cards_x = lanes_x + lane_gap * max(1, n_wires) + 290
    title = spec.get("title") or "Wiring"
    out_base.append(_t(uno_x, 40, title, 36, weight="700"))

    # The Arduino.
    if L.has_uno:
        x, y = uno_x, uno_y
        out_base.append(f'<rect x="{x}" y="{y}" width="{UNO_W}" height="{UNO_H}" rx="22" fill="#0b7285" stroke="#085566" stroke-width="3"/>')
        out_base.append(f'<rect x="{x - 18}" y="{y + 60}" width="70" height="80" rx="6" fill="#adb5bd" stroke="#495057" stroke-width="2"/>')
        out_base.append(_t(x + 17, y + 100, "USB", 15, "middle", "700", "#343a40"))
        out_base.append(f'<rect x="{x - 10}" y="{y + 250}" width="56" height="70" rx="6" fill="#343a40"/>')
        out_base.append(_t(x + UNO_W / 2 + 40, y + UNO_H / 2 - 12, "Arduino Uno", 40, "middle", "700", "#ffffff"))
        out_base.append(_t(x + UNO_W / 2 + 40, y + UNO_H / 2 + 26, "~ marks PWM pins", 20, "middle", "normal", "#c5f6fa"))
        start = x + 70
        for row, names, py in (("top", UNO_TOP, y + 26), ("bottom", UNO_BOTTOM, y + UNO_H - 26)):
            px = start + (60 if row == "bottom" else 0)
            for name in names:
                if name is None:
                    px += PIN * 0.6
                    continue
                out_base.append(f'<rect x="{px - 10}" y="{py - 10}" width="20" height="20" rx="3" fill="#212529" '
                                f'stroke="#e9ecef" stroke-width="1.5" class="pin" data-pin="{escape(name)}"/>')
                ty = py + 30 if row == "top" else py - 30
                label = ("~" if name in PWM else "") + name.replace("D", "", 1) if name.startswith("D") else name
                out_base.append(_t(px, ty, label, 17, "middle", "700", "#e3fafc",
                                   f' transform="rotate(-90 {px:.0f} {ty:.0f})"'))
                key = f"uno.{name}"
                if key not in L.pins:  # first GND wins
                    L.pins[key] = (px, py, row)
                px += PIN

    # The other parts, stacked on the right, pins on their left edge.
    cy = 90
    for card in L.cards:
        kind_key = str(card.get("type", "")).lower()
        kind = PARTS.get(kind_key, PARTS["generic"])
        pins = L._card_pins(card)
        card["_pins"] = pins
        h = max(130, 74 + 54 * len(pins))
        w = 330
        out_base.append(f'<rect x="{cards_x}" y="{cy}" width="{w}" height="{h}" rx="16" fill="#ffffff" '
                        f'stroke="#343a40" stroke-width="3"/>')
        name = card.get("label") or kind["name"]
        out_base.append(_t(cards_x + w / 2 + 20, cy + 28, name, 25, "middle", "700"))
        if card.get("value"):
            out_base.append(_t(cards_x + w / 2 + 20, cy + 54, card["value"], 20, "middle", "600", MUTED))
        out_base.append(_icon(kind_key, cards_x + w - 60, cy + h / 2 + 12))
        for i, pin in enumerate(pins):
            py = cy + 84 + 54 * i if len(pins) > 1 else cy + h / 2 + 10
            out_base.append(f'<circle cx="{cards_x}" cy="{py}" r="10" fill="#212529" stroke="#ffffff" stroke-width="2"/>')
            out_base.append(_t(cards_x + 20, py, pin, 22, weight="700"))
            L.pins[f"{card['id']}.{pin}"] = (cards_x, py, "card")
        cy += h + 40

    # Wires: each gets its own lane (and its own channel above or below the
    # board), so no two wires ever share a line.
    signal_i = 0
    legend = {}
    for i, wire in enumerate(L.wires):
        ends = []
        for end in (wire["from"], wire["to"]):
            part, pin = L._split(end)
            if part.lower() in L.uno_ids:
                name = norm_uno_pin(pin)
                ends.append(f"uno.{name}" if name else None)
            else:
                card = next((c for c in L.cards if c["id"] == part), None)
                match = L._match(card["_pins"], pin) if card else None
                ends.append(f"{part}.{match}" if match else None)
        if None in ends or any(e not in L.pins for e in ends):
            L.skipped.append(f"{wire['from']} -> {wire['to']}")
            continue
        a, b = ends
        colour = wire_colour(a, b, signal_i)
        if colour not in (POWER, GROUND):
            signal_i += 1
        lane = lanes_x + lane_gap * i
        pts = []
        for end in (a, b):
            x, y, side = L.pins[end]
            if side == "top":
                ch = uno_y - 30 - chan_gap * i
                pts.append([(x, y), (x, ch), (lane, ch)])
            elif side == "bottom":
                ch = uno_y + UNO_H + 30 + chan_gap * i
                pts.append([(x, y), (x, ch), (lane, ch)])
            else:
                pts.append([(x, y), (lane, y)])
        path = pts[0] + list(reversed(pts[1]))
        d = "M " + " L ".join(f"{x:.0f} {y:.0f}" for x, y in path)
        step = int(wire.get("step") or 0)
        g = steps.setdefault(step, [])
        g.append(f'<path d="{d}" fill="none" stroke="#ffffff" stroke-width="11" stroke-linejoin="round" stroke-linecap="round"/>')
        g.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="6" stroke-linejoin="round" '
                 f'stroke-linecap="round" class="wire"/>')
        for x, y in (path[0], path[-1]):
            g.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="8" fill="{colour}" stroke="#ffffff" stroke-width="2.5"/>')
        # Label: the pin pair, near where the wire reaches the part.
        text = wire.get("label") or f"{_pin_name(L, a)} to {_pin_name(L, b)}"
        card_end = path[-1] if L.pins[b][2] == "card" else path[0]
        g.append(_label(cards_x - 22, card_end[1] - 25, text[:24], colour, right=True))
        legend[{POWER: "Power (5V / VCC)", GROUND: "Ground (GND)"}.get(colour, "Signal")] = colour
        L.used.update(ends)

    # Light up the Arduino pins that are used.
    for end in L.used:
        if end.startswith("uno."):
            x, y, _ = L.pins[end]
            out_base.append(f'<rect x="{x - 13}" y="{y - 13}" width="26" height="26" rx="5" fill="none" '
                            f'stroke="#ffd43b" stroke-width="4"/>')

    # Legend.
    bottom = max(cy, (uno_y + UNO_H + 60 + chan_gap * n_wires) if L.has_uno else 0)
    lx = uno_x
    for name, colour in legend.items():
        out_base.append(f'<line x1="{lx}" y1="{bottom + 20}" x2="{lx + 44}" y2="{bottom + 20}" stroke="{colour}" '
                        f'stroke-width="7" stroke-linecap="round"/>')
        out_base.append(_t(lx + 56, bottom + 20, name, 20, weight="600"))
        lx += 100 + 11 * len(name)
    width = max(cards_x + 370, lx + 40)
    height = bottom + 60
    return _svg(width, height, out_base, steps), L.skipped


def _pin_name(L, end):
    """'uno.D9' -> 'D9'; 'r1.2' -> 'Resistor 2' (a bare number needs its part)."""
    part, pin = end.split(".", 1)
    if part == "uno" or not pin.isdigit():
        return pin
    card = next((c for c in L.cards if c["id"] == part), {})
    name = card.get("label") or PARTS.get(str(card.get("type", "")).lower(), PARTS["generic"])["name"]
    return f"{name.split()[0]} {pin}"


def _icon(kind, x, y):
    """A small picture of the part, so cards are told apart at a glance."""
    if kind == "servo":
        return (f'<rect x="{x - 26}" y="{y - 18}" width="52" height="36" rx="5" fill="#4dabf7"/>'
                f'<circle cx="{x - 8}" cy="{y}" r="9" fill="#ffffff"/><rect x="{x - 8}" y="{y - 4}" width="30" height="8" rx="4" fill="#ffffff"/>')
    if kind in ("led",):
        return (f'<circle cx="{x}" cy="{y - 6}" r="16" fill="#ff6b6b" stroke="#c92a2a" stroke-width="2"/>'
                f'<line x1="{x - 6}" y1="{y + 10}" x2="{x - 6}" y2="{y + 30}" stroke="#868e96" stroke-width="3"/>'
                f'<line x1="{x + 6}" y1="{y + 10}" x2="{x + 6}" y2="{y + 24}" stroke="#868e96" stroke-width="3"/>')
    if kind == "resistor":
        return (f'<line x1="{x - 34}" y1="{y}" x2="{x + 34}" y2="{y}" stroke="#868e96" stroke-width="3"/>'
                f'<rect x="{x - 20}" y="{y - 9}" width="40" height="18" rx="8" fill="#e9c46a"/>'
                + "".join(f'<rect x="{x - 12 + 8 * k}" y="{y - 9}" width="4" height="18" fill="{c}"/>'
                          for k, c in enumerate(("#c92a2a", "#c92a2a", "#5c3d2e"))))
    if kind == "button":
        return (f'<rect x="{x - 20}" y="{y - 20}" width="40" height="40" rx="4" fill="#495057"/>'
                f'<circle cx="{x}" cy="{y}" r="12" fill="#212529"/>')
    if kind in ("potentiometer",):
        return (f'<circle cx="{x}" cy="{y}" r="20" fill="#74c0fc" stroke="#1864ab" stroke-width="2"/>'
                f'<line x1="{x}" y1="{y}" x2="{x + 12}" y2="{y - 14}" stroke="#1864ab" stroke-width="4"/>')
    if kind in ("buzzer",):
        return f'<circle cx="{x}" cy="{y}" r="20" fill="#343a40"/><circle cx="{x}" cy="{y}" r="5" fill="#adb5bd"/>'
    if kind == "ultrasonic":
        return (f'<rect x="{x - 32}" y="{y - 14}" width="64" height="28" rx="4" fill="#1c7ed6"/>'
                f'<circle cx="{x - 15}" cy="{y}" r="11" fill="#dee2e6"/><circle cx="{x + 15}" cy="{y}" r="11" fill="#dee2e6"/>')
    return f'<rect x="{x - 22}" y="{y - 16}" width="44" height="32" rx="5" fill="#868e96"/>'


# ---------- flowcharts ----------

def render_flowchart(spec: dict):
    nodes = [n for n in spec.get("nodes", []) if isinstance(n, dict) and n.get("id")]
    edges = [e for e in spec.get("edges", []) if isinstance(e, dict) and e.get("from") and e.get("to")]
    base, steps, skipped = [], {}, []
    base.append(_t(60, 40, spec.get("title") or "Flowchart", 36, weight="700"))
    w, h, gap, x0 = 380, 84, 70, 140
    pos = {}
    y = 100
    for n in nodes:
        pos[n["id"]] = (x0 + w / 2, y + h / 2)
        shape = n.get("shape", "box")
        cx, cy = pos[n["id"]]
        if shape == "decision":
            base.append(f'<polygon points="{cx},{y - 8} {cx + w / 2},{cy} {cx},{y + h + 8} {cx - w / 2},{cy}" '
                        f'fill="#fff3bf" stroke="#e67700" stroke-width="3"/>')
        elif shape in ("start", "end"):
            base.append(f'<rect x="{x0}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="#d3f9d8" stroke="#2b8a3e" stroke-width="3"/>')
        else:
            base.append(f'<rect x="{x0}" y="{y}" width="{w}" height="{h}" rx="14" fill="#e7f5ff" stroke="#1971c2" stroke-width="3"/>')
        lines = _wrap(n.get("text") or n["id"], 28)[:2]
        for k, line in enumerate(lines):
            base.append(_t(cx, cy + (k - (len(lines) - 1) / 2) * 28, line, 23, "middle", "600"))
        y += h + gap
    index = {n["id"]: i for i, n in enumerate(nodes)}
    side = 0
    for e in edges:
        if e["from"] not in pos or e["to"] not in pos:
            skipped.append(f"{e['from']} -> {e['to']}")
            continue
        (ax, ay), (bx, by) = pos[e["from"]], pos[e["to"]]
        g = steps.setdefault(int(e.get("step") or 0), [])
        if index[e["to"]] == index[e["from"]] + 1:
            d = f"M {ax} {ay + h / 2} L {bx} {by - h / 2 - 6}"
            lx, ly = ax + 60, (ay + by) / 2
        else:  # loops and jumps go round the side, each on its own lane
            side += 1
            lane = x0 + w + 40 + 34 * side
            d = f"M {ax + w / 2} {ay} L {lane} {ay} L {lane} {by} L {bx + w / 2 + 6} {by}"
            lx, ly = lane, (ay + by) / 2
        g.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="4" marker-end="url(#arrow)" class="wire"/>')
        if e.get("label"):
            g.append(_label(lx, ly, e["label"], INK))
    width = x0 + w + 120 + 34 * side + 80
    return _svg(width, y + 20, base, steps), skipped


def _wrap(text, n):
    words, lines, cur = str(text).split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > n and cur:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    return lines + ([cur] if cur else [])


# ---------- both ----------

def _svg(width, height, base, steps):
    defs = ('<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerUnits="userSpaceOnUse" '
            'markerWidth="18" markerHeight="18" '
            f'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{INK}"/></marker></defs>')
    groups = "".join(f'<g id="step-{n}">{"".join(items)}</g>' for n, items in sorted(steps.items()) if n > 0)
    always = "".join(steps.get(0, []))
    return (f'<svg viewBox="0 0 {width:.0f} {height:.0f}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="{FONT}">{defs}<rect width="100%" height="100%" fill="#ffffff"/>'
            f'<g id="base">{"".join(base)}{always}</g>{groups}</svg>')


def render(spec: dict):
    """(svg, list of wires/edges that couldn't be drawn)."""
    if str(spec.get("kind", "")).lower() == "flowchart" or (spec.get("nodes") and not spec.get("wires")):
        return render_flowchart(spec)
    return render_wiring(spec)
