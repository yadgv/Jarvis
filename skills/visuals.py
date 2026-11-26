"""More whiteboard drawings: mind maps and timelines.

Like skills/diagram.py, the model only describes what to draw as JSON and
these functions lay it out neatly. Each one returns (svg, problems) and puts
every part that gets its own spoken step into a <g id="step-N"> group, so the
whiteboard draws them one by one while Jarvis explains.
"""
from html import escape

from skills.diagram import INK, MUTED, SIGNALS, FONT, _svg, _t, _wrap, _clip, plain

KINDS = ("mindmap", "timeline")


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
        return _svg(800, 400, [_t(60, 44, spec.get("title") or "Mind map", 34, weight="700")], {}), ["no branches"]
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
        return _svg(800, 400, [_t(60, 44, title, 34, weight="700")], {}), ["no events"]
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
    return []


def render(spec: dict):
    kind = str(spec.get("kind") or "").lower()
    return {"mindmap": render_mindmap, "timeline": render_timeline}[kind](spec)
