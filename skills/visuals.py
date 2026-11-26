"""More whiteboard drawings: mind maps and timelines.

Like skills/diagram.py, the model only describes what to draw as JSON and
these functions lay it out neatly. Each one returns (svg, problems) and puts
every part that gets its own spoken step into a <g id="step-N"> group, so the
whiteboard draws them one by one while Jarvis explains.
"""
import ast
import math
import re

from skills.diagram import INK, MUTED, SIGNALS, _svg, _t, _wrap, _clip, plain

_ALIASES = {"mind map": "mindmap", "mind_map": "mindmap", "graph": "plot", "function": "plot", "fbd": "forces",
            "free-body": "forces", "free_body": "forces", "free body": "forces", "schematic": "circuit"}
KINDS = ("mindmap", "timeline", "plot", "forces", "circuit") + tuple(_ALIASES)


def _width(text, size, bold=False):
    """A rough width for text in Segoe UI, good enough for laying out boxes."""
    return len(str(text)) * size * (0.58 if bold else 0.52)


def _tint(colour):
    """A pale version of a colour for box fills."""
    c = colour.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(v + (255 - v) * 0.85) for v in (r, g, b))


# ---------- mind maps ----------

def _branches(spec):
    out = []
    for b in spec.get("branches") or []:
        if isinstance(b, str):
            b = {"text": b}
        if not isinstance(b, dict) or not str(b.get("text") or b.get("name") or "").strip():
            continue
        kids = []
        for c in b.get("children") or []:
            c = c.get("text") or c.get("name") if isinstance(c, dict) else c
            if str(c or "").strip():
                kids.append(str(c).strip())
        out.append({"text": str(b.get("text") or b.get("name")).strip(), "children": kids[:6]})
    return out[:8]


def render_mindmap(spec: dict):
    """A centre idea with branches out to both sides, and each branch's
    smaller ideas beside it. One step per branch."""
    branches = _branches(spec)
    if not branches:
        raise ValueError("no branches")
    centre = plain(spec.get("center") or spec.get("centre") or spec.get("title") or "Idea")
    right = branches[0::2]
    left = branches[1::2]
    row, gap = 44, 34

    def block(b):
        return max(1, len(b["children"])) * row + gap

    height = max(sum(block(b) for b in side) for side in (right, left or [{"children": []}]))
    H = max(460, height + 170)
    lines = _wrap(centre, 18)[:3]
    cw = min(340, max(200, max(_width(l, 26, True) for l in lines) + 60))

    def reach(items):  # how far a side spreads out from the centre
        return max([cw / 2 + 110 + max(140, _width(_clip(plain(b["text"]), 26), 22, True) + 44)
                    + (84 + max(_width(_clip(plain(k), 34), 19) for k in b["children"]) if b["children"] else 0)
                    for b in items] or [cw / 2])

    cx = 60 + reach(left)
    W = max(cx + reach(right) + 60, _width(spec.get("title") or "", 34, True) + 140)
    cy = 110 + (H - 150) / 2
    ch = 54 + 30 * len(lines)
    base = [_t(60, 44, spec.get("title") or "Mind map", 34, weight="700")]
    base.append(f'<rect x="{cx - cw / 2:.0f}" y="{cy - ch / 2:.0f}" width="{cw:.0f}" height="{ch:.0f}" rx="{ch / 2:.0f}" '
                f'fill="#fff3bf" stroke="#e67700" stroke-width="4"/>')
    for k, line in enumerate(lines):
        base.append(_t(cx, cy + (k - (len(lines) - 1) / 2) * 30, line, 26, "middle", "700"))
    steps = {}
    n = 0
    for side, items in ((1, right), (-1, left)):
        total = sum(block(b) for b in items)
        y = cy - total / 2
        for b in items:
            n = branches.index(b) + 1
            colour = SIGNALS[(n - 1) % len(SIGNALS)]
            g = steps.setdefault(n, [])
            by = y + block(b) / 2 - gap / 2
            y += block(b)
            text = _clip(plain(b["text"]), 26)
            bw = max(140, _width(text, 22, True) + 44)
            bx = cx + side * (cw / 2 + 110)          # inner edge of the branch box
            x0 = bx if side > 0 else bx - bw
            sx = cx + side * cw / 2 * 0.92
            g.append(f'<path d="M {sx:.0f} {cy:.0f} C {sx + side * 70:.0f} {cy:.0f} {bx - side * 70:.0f} {by:.0f} '
                     f'{bx:.0f} {by:.0f}" fill="none" stroke="{colour}" stroke-width="5" stroke-linecap="round" class="wire"/>')
            g.append(f'<rect x="{x0:.0f}" y="{by - 26:.0f}" width="{bw:.0f}" height="52" rx="14" fill="{_tint(colour)}" '
                     f'stroke="{colour}" stroke-width="3"/>')
            g.append(_t(x0 + bw / 2, by, text, 22, "middle", "700"))
            outer = x0 + bw if side > 0 else x0
            kids = b["children"]
            for i, kid in enumerate(kids):
                ky = by + (i - (len(kids) - 1) / 2) * row
                kx = outer + side * 70
                g.append(f'<path d="M {outer:.0f} {by:.0f} C {outer + side * 35:.0f} {by:.0f} {kx - side * 35:.0f} {ky:.0f} '
                         f'{kx:.0f} {ky:.0f}" fill="none" stroke="{colour}" stroke-width="3" class="wire"/>')
                g.append(f'<circle cx="{kx:.0f}" cy="{ky:.0f}" r="5" fill="{colour}"/>')
                g.append(_t(kx + side * 14, ky, _clip(plain(kid), 34), 19, "start" if side > 0 else "end"))
    return _svg(W, H, base, steps), []


# ---------- timelines ----------

def _events(spec):
    out = []
    for e in spec.get("events") or []:
        if isinstance(e, str):
            e = {"text": e}
        if not isinstance(e, dict):
            continue
        text = str(e.get("text") or e.get("title") or e.get("event") or "").strip()
        date = str(e.get("date") or e.get("year") or e.get("when") or "").strip()
        if text or date:
            out.append({"date": date, "text": text, "detail": str(e.get("detail") or "").strip()})
    return out[:16]


def render_timeline(spec: dict):
    """Events along a line, in order, alternating above and below it.
    One step per event."""
    events = _events(spec)
    title = spec.get("title") or "Timeline"
    if not events:
        raise ValueError("no events")
    gap = 230
    W = max(1000, 160 + gap * len(events))
    H = 700
    axis = 380
    base = [_t(60, 44, title, 34, weight="700")]
    x_first, x_last = 120, 120 + gap * (len(events) - 1)
    base.append(f'<line x1="{x_first - 50}" y1="{axis}" x2="{x_last + 70}" y2="{axis}" stroke="{INK}" '
                f'stroke-width="5" stroke-linecap="round" marker-end="url(#arrow)"/>')
    steps = {}
    for i, e in enumerate(events):
        n = i + 1
        colour = SIGNALS[i % len(SIGNALS)]
        x = 120 + gap * i
        up = i % 2 == 0
        end = axis - 70 if up else axis + 70
        g = steps.setdefault(n, [])
        g.append(f'<path d="M {x} {axis} L {x} {end}" fill="none" stroke="{colour}" stroke-width="4" class="wire"/>')
        g.append(f'<circle cx="{x}" cy="{axis}" r="11" fill="{colour}" stroke="#fff" stroke-width="3"/>')
        lines = _wrap(plain(e["text"]), 18)[:3]
        detail = _wrap(plain(e["detail"]), 24)[:2] if e["detail"] else []
        rows = [(e["date"], 24, "700", colour)] if e["date"] else []
        rows += [(l, 20, "600", INK) for l in lines] + [(l, 17, "normal", MUTED) for l in detail]
        h = 24 + sum(r[1] + 10 for r in rows)
        top = end - h if up else end
        g.append(f'<rect x="{x - 106}" y="{top:.0f}" width="212" height="{h:.0f}" rx="12" fill="{_tint(colour)}" '
                 f'stroke="{colour}" stroke-width="2.5"/>')
        y = top + 12
        for text, size, weight, fill in rows:
            y += (size + 10) / 2
            g.append(_t(x, y, _clip(text, 26), size, "middle", weight, fill))
            y += (size + 10) / 2
    return _svg(W, H, base, steps), []


def default_steps(spec: dict):
    """Spoken steps for a drawing whose spec has none."""
    kind = str(spec.get("kind") or "").lower()
    if kind == "mindmap":
        return [b["text"] + (": " + ", ".join(b["children"]) + "." if b["children"] else ".")
                for b in _branches(spec)]
    if kind == "timeline":
        return [(f"{e['date']}: " if e["date"] else "") + (e["text"] or "") for e in _events(spec)]
    if kind in ("plot", "graph", "function"):
        return [f"The graph of {f.get('label') or f.get('expr')}." if isinstance(f, dict) else f"The graph of {f}."
                for f in spec.get("functions") or []]
    if kind in ("forces", "fbd", "free-body", "free_body", "free body"):
        return [f"{f.get('name') or 'A force'}" + (f", {f['value']}" if f.get("value") else "") + "."
                for f in spec.get("forces") or [] if isinstance(f, dict)]
    return []


def render(spec: dict):
    kind = str(spec.get("kind") or "").lower()
    kind = _ALIASES.get(kind, kind)
    return {"mindmap": render_mindmap, "timeline": render_timeline, "plot": render_plot, "forces": render_forces,
            "circuit": render_circuit}[kind](spec)


# ---------- function plots ----------

_FUNCS = {n: getattr(math, n) for n in ("sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
                                         "sqrt", "exp", "log10", "log2", "floor", "ceil")}
_FUNCS.update(abs=abs, ln=math.log, log=math.log10, arcsin=math.asin, arccos=math.acos, arctan=math.atan)
_CONST = {"pi": math.pi, "e": math.e}
_OPS = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load, ast.Constant, ast.Add, ast.Sub,
        ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd, ast.FloorDiv)


def _expr(text):
    """'y = 2x^2 - 3sin(x)' -> a safe function of x, or None. Only numbers,
    x, + - * / ^, brackets and maths functions; nothing else runs."""
    t = str(text or "").lower().replace("^", "**").replace("−", "-").replace("×", "*").replace("·", "*")
    t = re.sub(r"^\s*(?:y|f\s*\(\s*x\s*\))\s*=", "", t).strip()
    t = re.sub(r"(\d)\s*([a-z(])", r"\1*\2", t)          # 2x -> 2*x, 3sin -> 3*sin, 2( -> 2*(
    t = re.sub(r"\)\s*([a-z0-9(])", r")*\1", t)          # (x+1)(x-1)
    t = re.sub(r"\bx\s*([a-z(])", r"x*\1", t)            # x sin(x)
    if not t or len(t) > 200:
        return None
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, _OPS):
            return None
        if isinstance(node, ast.Name) and node.id not in _FUNCS and node.id not in _CONST and node.id != "x":
            return None
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS):
            return None
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            return None
        if isinstance(node, ast.Constant):
            node.value = float(node.value)   # float powers overflow at once; huge int powers would hang
    code = compile(tree, "<plot>", "eval")

    def f(x):
        try:
            v = eval(code, {"__builtins__": {}}, dict(_FUNCS, **_CONST, x=x))  # noqa: S307 (checked above)
            v = float(v)
            return v if math.isfinite(v) else None
        except (ArithmeticError, ValueError, TypeError, OverflowError):
            return None
    return f


def _pair(v, default):
    try:
        a, b = float(v[0]), float(v[1])
        return (a, b) if b > a else default
    except (TypeError, ValueError, IndexError, KeyError):
        return default


def _nice(span):
    raw = span / 8
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)


def render_plot(spec: dict):
    """Graphs of functions of x on a grid, one step per function, then the
    marked points (roots, a maximum, where two lines cross)."""
    title = spec.get("title") or "Graph"
    funcs, problems = [], []
    for item in (spec.get("functions") or [])[:6]:
        item = {"expr": item} if isinstance(item, str) else item
        if not isinstance(item, dict):
            continue
        f = _expr(item.get("expr") or item.get("y"))
        if f:
            funcs.append((f, plain(item.get("label") or item.get("expr") or "")))
        else:
            problems.append(f"can't plot {item.get('expr')!r}")
    if not funcs:
        raise ValueError(problems[0] if problems else "nothing to plot")
    x0, x1 = _pair(spec.get("x_range"), (-10.0, 10.0))
    xs = [x0 + (x1 - x0) * i / 600 for i in range(601)]
    ys = [[f(x) for x in xs] for f, _ in funcs]
    if spec.get("y_range"):
        y0, y1 = _pair(spec["y_range"], (-10.0, 10.0))
    else:
        vals = sorted(v for row in ys for v in row if v is not None)
        if not vals:
            raise ValueError("no real values in that range")
        lo, hi = vals[int(len(vals) * 0.03)], vals[int(len(vals) * 0.97) - 1]   # ignore asymptotes
        lo, hi = min(lo, 0) if lo > -abs(hi) * 4 else lo, max(hi, 0) if hi < abs(lo) * 4 else hi
        pad = (hi - lo) * 0.1 or 1
        y0, y1 = lo - pad, hi + pad
    W, H = 1200, 820
    L, R, T, B = 110, W - 60, 100, H - 90

    def px(x):
        return L + (x - x0) / (x1 - x0) * (R - L)

    def py(y):
        return B - (y - y0) / (y1 - y0) * (B - T)

    base = [_t(60, 44, title, 34, weight="700")]
    for lo_, hi_, to, axis in ((x0, x1, px, "x"), (y0, y1, py, "y")):
        step = _nice(hi_ - lo_)
        v = math.ceil(lo_ / step) * step
        while v <= hi_ + 1e-9:
            p = to(v)
            label = f"{v:g}" if abs(v) > 1e-9 else "0"
            if axis == "x":
                base.append(f'<line x1="{p:.1f}" y1="{T}" x2="{p:.1f}" y2="{B}" stroke="#e9ecef" stroke-width="1.5"/>')
                base.append(_t(p, B + 26, label, 17, "middle", fill=MUTED))
            else:
                base.append(f'<line x1="{L}" y1="{p:.1f}" x2="{R}" y2="{p:.1f}" stroke="#e9ecef" stroke-width="1.5"/>')
                base.append(_t(L - 12, p, label, 17, "end", fill=MUTED))
            v += step
    if x0 <= 0 <= x1:
        base.append(f'<line x1="{px(0):.1f}" y1="{B}" x2="{px(0):.1f}" y2="{T - 10}" stroke="{INK}" stroke-width="2.5" '
                    f'marker-end="url(#arrow)"/>')
    if y0 <= 0 <= y1:
        base.append(f'<line x1="{L}" y1="{py(0):.1f}" x2="{R + 10}" y2="{py(0):.1f}" stroke="{INK}" stroke-width="2.5" '
                    f'marker-end="url(#arrow)"/>')
    base.append(_t((L + R) / 2, H - 30, spec.get("x_label") or "x", 20, "middle", "600"))
    base.append(_t(36, (T + B) / 2, spec.get("y_label") or "y", 20, "middle", "600"))
    base.append(f'<clipPath id="plotarea"><rect x="{L}" y="{T}" width="{R - L}" height="{B - T}"/></clipPath>')
    legend_w = max(_width(label, 20, True) for _, label in funcs) + 70
    base.append(f'<rect x="{L + 6}" y="{T + 2}" width="{legend_w:.0f}" height="{34 * len(funcs) + 8}" rx="8" '
                f'fill="#fff" fill-opacity="0.9"/>')
    steps = {}
    for k, ((f, label), row) in enumerate(zip(funcs, ys)):
        colour = SIGNALS[(k + 1) % len(SIGNALS)]
        d, pen, prev = [], False, None
        for x, y in zip(xs, row):
            if y is None or (prev is not None and abs(py(y) - py(prev)) > (B - T) * 1.5):
                pen, prev = False, y
                continue
            yy = max(T - 400, min(B + 400, py(y)))
            d.append(f'{"L" if pen else "M"} {px(x):.1f} {yy:.1f}')
            pen, prev = True, y
        g = steps.setdefault(k + 1, [])
        g.append(f'<g clip-path="url(#plotarea)"><path d="{" ".join(d)}" fill="none" stroke="{colour}" '
                 f'stroke-width="4" stroke-linejoin="round" class="wire"/></g>')
        g.append(f'<rect x="{L + 16}" y="{T + 14 + 34 * k}" width="26" height="6" rx="3" fill="{colour}"/>'
                 + _t(L + 52, T + 17 + 34 * k, label, 20, weight="600", extra=' paint-order="stroke" stroke="#fff" stroke-width="6"'))
    points = [p for p in spec.get("points") or [] if isinstance(p, dict)]
    if points:
        g = steps.setdefault(len(funcs) + 1, [])
        for p in points[:10]:
            try:
                x, y = float(p["x"]), float(p["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            g.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="8" fill="{INK}" stroke="#fff" stroke-width="3"/>')
            g.append(_t(px(x) + 14, py(y) - 20, p.get("label") or f"({x:g}, {y:g})", 19, weight="700",
                        extra=' paint-order="stroke" stroke="#fff" stroke-width="6"'))
    return _svg(W, H, base, steps), problems


# ---------- free-body diagrams ----------

_DIRS = {"right": 0, "east": 0, "up": 90, "north": 90, "left": 180, "west": 180, "down": 270, "south": 270}


def _angle(direction, slope):
    """A force's direction in degrees (0 = right, 90 = up). Words work too,
    and on a slope: 'up the slope', 'down the slope', 'normal', 'into the slope'."""
    if isinstance(direction, (int, float)):
        return float(direction)
    d = str(direction or "").lower().strip()
    try:
        return float(d.replace("°", "").replace("deg", ""))
    except ValueError:
        pass
    if "slope" in d or "incline" in d or "plane" in d or d in ("normal", "perpendicular"):
        if "down" in d:
            return 180 + slope
        if "up" in d and "perp" not in d:
            return slope
        if "into" in d:
            return 270 + slope
        return 90 + slope                     # normal: straight out of the slope
    for word, a in _DIRS.items():
        if word in d:
            return a
    return 270.0


def render_forces(spec: dict):
    """A block (flat ground, a slope, or hanging in the air) with an arrow for
    every force acting on it, scaled by size. One step per force."""
    title = spec.get("title") or "Free-body diagram"
    forces = [f for f in spec.get("forces") or [] if isinstance(f, dict)][:8]
    if not forces:
        raise ValueError("no forces")
    surface = str(spec.get("surface") or "flat").lower()
    try:
        slope = float(spec.get("angle") or 0) if "incl" in surface or "slope" in surface or "ramp" in surface else 0.0
    except (TypeError, ValueError):
        slope = 0.0
    W, H = 1200, 860
    cx, cy = 600, 430
    base = [_t(60, 44, title, 34, weight="700")]
    rad = math.radians(slope)
    if slope:
        ux, uy = math.cos(rad), -math.sin(rad)            # up the slope, screen coords
        nx, ny = -math.sin(rad), -math.cos(rad)           # out of the slope
        bx, by = cx - nx * 60, cy - ny * 60               # a point on the slope under the block
        p1 = (bx - ux * 520, by - uy * 520)
        p2 = (bx + ux * 420, by + uy * 420)
        base.append(f'<polygon points="{p1[0]:.0f},{p1[1]:.0f} {p2[0]:.0f},{p2[1]:.0f} {p2[0]:.0f},{p1[1]:.0f}" '
                    f'fill="#f1f3f5" stroke="{MUTED}" stroke-width="3"/>')
        base.append(f'<path d="M {p1[0] + 110:.0f} {p1[1]:.0f} A 110 110 0 0 0 {p1[0] + 110 * math.cos(rad):.0f} '
                    f'{p1[1] - 110 * math.sin(rad):.0f}" fill="none" stroke="{MUTED}" stroke-width="2.5"/>')
        base.append(_t(p1[0] + 130, p1[1] - 24, f"{slope:g}°", 20, weight="600", fill=MUTED))
    elif "hang" not in surface and "air" not in surface and "none" not in surface:
        base.append(f'<line x1="{cx - 420}" y1="{cy + 60}" x2="{cx + 420}" y2="{cy + 60}" stroke="{MUTED}" stroke-width="4"/>')
        for i in range(-410, 420, 40):
            base.append(f'<line x1="{cx + i}" y1="{cy + 60}" x2="{cx + i - 22}" y2="{cy + 84}" stroke="#ced4da" stroke-width="2.5"/>')
    obj = plain(spec.get("object") or "")
    base.append(f'<g transform="rotate({-slope:g} {cx} {cy})"><rect x="{cx - 80}" y="{cy - 60}" width="160" height="120" '
                f'rx="10" fill="#e7f5ff" stroke="#1971c2" stroke-width="4"/></g>')
    if obj:
        base.append(_t(cx, cy, _clip(obj, 14), 22, "middle", "700"))
    sizes = []
    for f in forces:
        try:
            sizes.append(abs(float(f.get("magnitude") or 1)))
        except (TypeError, ValueError):
            sizes.append(1.0)
    biggest = max(sizes) or 1
    steps = {}
    for k, (f, size) in enumerate(zip(forces, sizes)):
        a = math.radians(_angle(f.get("direction"), slope))
        length = 90 + 150 * size / biggest
        dx, dy = math.cos(a), -math.sin(a)
        # Arrows start at the edge of the block, so its name stays readable.
        u, v = abs(math.cos(a - rad)), abs(math.sin(a - rad))
        start = min(80 / u if u > 1e-6 else 1e9, 60 / v if v > 1e-6 else 1e9)
        sx, sy = cx + dx * start, cy + dy * start
        ex, ey = cx + dx * (start + length), cy + dy * (start + length)
        colour = SIGNALS[k % len(SIGNALS)]
        g = steps.setdefault(k + 1, [])
        g.append(f'<path d="M {sx:.0f} {sy:.0f} L {ex:.0f} {ey:.0f}" stroke="{colour}" stroke-width="7" '
                 f'stroke-linecap="round" marker-end="url(#arrow-{k})" class="wire"/>')
        g.append(f'<defs><marker id="arrow-{k}" viewBox="0 0 10 10" refX="7" refY="5" markerUnits="userSpaceOnUse" '
                 f'markerWidth="26" markerHeight="26" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{colour}"/>'
                 f'</marker></defs>')
        name = plain(f.get("name") or f.get("symbol") or f"F{k + 1}")
        value = plain(f.get("value") or "")
        lx, ly = ex + dx * 30, ey + dy * 30
        anchor = "start" if dx > 0.35 else "end" if dx < -0.35 else "middle"
        g.append(_t(lx, ly - (12 if value else 0), name, 22, anchor, "700", colour,
                    ' paint-order="stroke" stroke="#fff" stroke-width="6"'))
        if value:
            g.append(_t(lx, ly + 16, value, 19, anchor, "600", INK, ' paint-order="stroke" stroke="#fff" stroke-width="6"'))
    if spec.get("net"):
        steps.setdefault(len(forces) + 1, []).append(_t(60, H - 40, "Net force: " + plain(spec["net"]), 24, weight="700"))
    return _svg(W, H, base, steps), []


# ---------- circuit schematics ----------

SYMBOL_W = 150


def _part_kind(p):
    t = str(p.get("type") or p.get("kind") or "resistor").lower()
    for k in ("resistor", "lamp", "bulb", "led", "diode", "capacitor", "switch", "ammeter", "voltmeter", "motor",
              "buzzer", "fuse", "inductor", "battery", "cell"):
        if k in t:
            return {"bulb": "lamp", "cell": "battery"}.get(k, k)
    return "box"


def _symbol(kind, x, y, colour=INK):
    """A component symbol lying along a wire from x to x+SYMBOL_W at height y."""
    m = x + SYMBOL_W / 2
    s = f'stroke="{colour}" stroke-width="3.5" fill="none" stroke-linejoin="round"'
    lead = lambda a, b: f'<path d="M {a:.0f} {y} L {b:.0f} {y}" {s} class="wire"/>'  # noqa: E731
    if kind == "resistor":
        pts = " ".join(f"{m - 45 + 10 * i:.0f},{y + (0 if i in (0, 9) else (-14 if i % 2 else 14))}" for i in range(10))
        return lead(x, m - 45) + f'<polyline points="{pts}" {s}/>' + lead(m + 45, x + SYMBOL_W)
    if kind in ("lamp", "ammeter", "voltmeter", "motor"):
        inner = {"lamp": f'<path d="M {m - 16} {y - 16} L {m + 16} {y + 16} M {m - 16} {y + 16} L {m + 16} {y - 16}" {s}/>',
                 "ammeter": _t(m, y + 1, "A", 24, "middle", "700"), "voltmeter": _t(m, y + 1, "V", 24, "middle", "700"),
                 "motor": _t(m, y + 1, "M", 24, "middle", "700")}[kind]
        return lead(x, m - 24) + f'<circle cx="{m}" cy="{y}" r="24" fill="#fff" stroke="{colour}" stroke-width="3.5"/>' \
            + inner + lead(m + 24, x + SYMBOL_W)
    if kind in ("diode", "led"):
        out = (lead(x, m - 18) + f'<path d="M {m - 18} {y - 18} L {m - 18} {y + 18} L {m + 14} {y} Z" fill="#fff" stroke="{colour}" '
               f'stroke-width="3.5" stroke-linejoin="round"/>'
               + f'<path d="M {m + 14} {y - 18} L {m + 14} {y + 18}" {s}/>' + lead(m + 14, x + SYMBOL_W))
        if kind == "led":
            for o in (0, 14):
                out += (f'<path d="M {m - 2 + o} {y - 24} L {m + 12 + o} {y - 40} M {m + 4 + o} {y - 40} L {m + 12 + o} {y - 40} '
                        f'L {m + 12 + o} {y - 32}" {s}/>')
        return out
    if kind == "capacitor":
        return (lead(x, m - 8) + f'<path d="M {m - 8} {y - 24} L {m - 8} {y + 24} M {m + 8} {y - 24} L {m + 8} {y + 24}" {s}/>'
                + lead(m + 8, x + SYMBOL_W))
    if kind == "switch":
        return (lead(x, m - 30) + f'<circle cx="{m - 30}" cy="{y}" r="5" fill="{colour}"/>'
                + f'<path d="M {m - 30} {y} L {m + 26} {y - 26}" {s}/><circle cx="{m + 30}" cy="{y}" r="5" fill="{colour}"/>'
                + lead(m + 30, x + SYMBOL_W))
    if kind == "inductor":
        arcs = " ".join(f"a 10 10 0 0 1 20 0" for _ in range(4))
        return lead(x, m - 40) + f'<path d="M {m - 40} {y} {arcs}" {s}/>' + lead(m + 40, x + SYMBOL_W)
    if kind == "fuse":
        return lead(x, x + SYMBOL_W) + f'<rect x="{m - 32}" y="{y - 12}" width="64" height="24" fill="#fff" stroke="{colour}" stroke-width="3.5"/>'
    if kind == "battery":
        return (lead(x, m - 8) + f'<path d="M {m - 8} {y - 28} L {m - 8} {y + 28}" {s}/>'
                + f'<path d="M {m + 8} {y - 14} L {m + 8} {y + 14}" stroke="{colour}" stroke-width="7"/>'
                + lead(m + 8, x + SYMBOL_W) + _t(m - 22, y - 30, "+", 22, "middle", "700"))
    return (lead(x, m - 40) + f'<rect x="{m - 40}" y="{y - 20}" width="80" height="40" rx="6" fill="#fff" '
            f'stroke="{colour}" stroke-width="3.5"/>' + lead(m + 40, x + SYMBOL_W))


def _part_label(p, x, y, below=False):
    name = plain(p.get("label") or p.get("id") or "")
    value = plain(p.get("value") or "")
    text = " ".join(t for t in (name, value) if t)
    return _t(x + SYMBOL_W / 2, y + (44 if below else -44), _clip(text, 20), 19, "middle", "600") if text else ""


def render_circuit(spec: dict):
    """A schematic: a battery on the left, parts in series along the top wire,
    and parallel groups as rungs of a ladder. One step per series item.
    spec: {"source": {"type": "battery", "value": "9 V"},
           "series": [{"id": "R1", "type": "resistor", "value": "220 ohm"},
                      {"parallel": [[{"id": "L1", "type": "lamp"}], [{"id": "L2", "type": "lamp"}]]}]}"""
    title = spec.get("title") or "Circuit"
    items = []
    for it in (spec.get("series") or spec.get("components") or [])[:8]:
        if isinstance(it, dict) and isinstance(it.get("parallel"), list):
            branches = [[p for p in (b if isinstance(b, list) else [b]) if isinstance(p, dict)][:3]
                        for b in it["parallel"][:4]]
            branches = [b for b in branches if b]
            if branches:
                items.append(branches)
        elif isinstance(it, dict):
            items.append([[it]])
    if not items:
        raise ValueError("no parts")
    rung = 130
    left, top = 140, 170
    widths = [max(len(b) for b in item) * SYMBOL_W + (100 if len(item) > 1 else 0) for item in items]
    right = left + 60 + sum(widths) + 60
    depth = max(len(item) for item in items)
    bottom = top + max(2, depth) * rung + 40
    W, H = right + 140, bottom + 90
    src = spec.get("source") if isinstance(spec.get("source"), dict) else {"type": "battery", "value": spec.get("source") or ""}
    base = [_t(60, 44, title, 34, weight="700")]
    # The battery stands on the left side, + at the top.
    my = (top + bottom) / 2
    base.append(f'<g transform="rotate(90 {left} {my})">{_symbol("battery", left - SYMBOL_W / 2, my)}</g>')
    base.append(f'<path d="M {left} {top} L {left} {my - SYMBOL_W / 2} M {left} {my + SYMBOL_W / 2} L {left} {bottom} '
                f'L {right} {bottom} L {right} {top}" stroke="{INK}" stroke-width="3.5" fill="none"/>')
    label = " ".join(plain(t) for t in (src.get("label") or src.get("id") or "", src.get("value") or "") if t)
    if label:
        base.append(_t(left - 52, my, _clip(label, 14), 20, "end", "600"))
    steps = {}
    x = left
    for n, (item, w) in enumerate(zip(items, widths), 1):
        colour = SIGNALS[(n - 1) % len(SIGNALS)]
        g = steps.setdefault(n, [])
        start = x + (60 if n == 1 else 0)
        if n == 1:
            g.append(f'<path d="M {left} {top} L {start} {top}" stroke="{INK}" stroke-width="3.5" fill="none" class="wire"/>')
        if len(item) == 1:
            px_ = start
            for p in item[0]:
                g.append(_symbol(_part_kind(p), px_, top, colour))
                g.append(_part_label(p, px_, top))
                px_ += SYMBOL_W
            g.append(f'<path d="M {px_} {top} L {start + w} {top}" stroke="{INK}" stroke-width="3.5" fill="none" class="wire"/>')
        else:
            a, b = start + 50, start + w - 50
            last = top + rung * (len(item) - 1)
            g.append(f'<path d="M {a} {top} L {a} {last} M {b} {top} L {b} {last}" stroke="{INK}" stroke-width="3.5" '
                     f'fill="none" class="wire"/>')
            g.append(f'<circle cx="{a}" cy="{top}" r="6" fill="{INK}"/><circle cx="{b}" cy="{top}" r="6" fill="{INK}"/>')
            for r, branch in enumerate(item):
                y = top + rung * r
                span = len(branch) * SYMBOL_W
                px_ = a + (b - a - span) / 2
                g.append(f'<path d="M {a - (50 if not r else 0)} {y} L {px_} {y} M {px_ + span} {y} '
                         f'L {b + (50 if not r else 0)} {y}" stroke="{INK}" stroke-width="3.5" fill="none" class="wire"/>')
                for p in branch:
                    g.append(_symbol(_part_kind(p), px_, y, colour))
                    g.append(_part_label(p, px_, y, below=bool(r)))
                    px_ += SYMBOL_W
        x = start + w
    if x < right:
        steps[len(items)].append(f'<path d="M {x} {top} L {right} {top}" stroke="{INK}" stroke-width="3.5" fill="none" class="wire"/>')
    return _svg(W, H, base, steps), []
