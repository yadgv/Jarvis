"""The whiteboard's holographic look: recolours the diagrams (drawn in light
"paper" colours by diagram.py and visuals.py) for a dark glass HUD, so the
drawing code stays the same and saved/exported pictures keep their colours.

Lines become glowing cyan, cards dark translucent glass, text pale blue-white;
the signal colours (wires, series) stay, a little brighter."""
import re

BG = "#050b10"
GLASS = "#0a1a24"
CYAN = "#5fe1ff"
TEXT_HI = "#e4f8ff"
TEXT_LO = "#8db4c6"

# fill colours of shapes (cards, boards, chips)
SHAPE_FILL = {
    "#ffffff": GLASS, "#fff": GLASS, "#f1f3f5": "#0e202b",
    "#fff3bf": "#2a2108", "#d3f9d8": "#0a2a1c", "#e7f5ff": "#0a2232", "#fff4e6": "#2a1708",
    "#0b7285": "#063542", "#adb5bd": "#1d3340", "#343a40": "#12242e", "#212529": "#07131a",
    "#495057": "#1a2c36", "#dee2e6": "#9fd8ea", "#868e96": "#3b5a6a",
    "#1d2433": CYAN,  # arrow heads
    "#1c7ed6": "#2f9cff", "#4dabf7": "#3fb4ff", "#74c0fc": "#3fc3ff",
}
# outline colours
STROKE = {
    "#ffffff": BG, "#fff": BG,                 # the dark halo that lifts wires off what's under them
    "#1d2433": CYAN, "#343a40": CYAN, "#085566": CYAN, "#1971c2": "#3fb6ff", "#1864ab": "#3fb6ff",
    "#2b8a3e": "#3ee69a", "#e67700": "#ffb84a", "#495057": "#4f7486", "#868e96": "#6d8fa0",
    "#e9ecef": "#14303d", "#ced4da": "#1e4050", "#111111": "#c9d7de", "#ffd43b": "#ffe066",
    "#5b6678": TEXT_LO,
}
# text colours
TEXT = {
    "#1d2433": TEXT_HI, "#ffffff": TEXT_HI, "#fff": TEXT_HI, "#343a40": "#bfeeff",
    "#5b6678": TEXT_LO, "#e03131": "#ff6b7a",
}
# the signal colours, a touch brighter on black
BRIGHTER = {
    "#f08c00": "#ffa630", "#1c7ed6": "#3fa4ff", "#2f9e44": "#3ee07a", "#9c36b5": "#c77dff",
    "#0c8599": "#22d3ee", "#d6336c": "#ff5c93", "#5f3dc4": "#8f7bff", "#e8590c": "#ff7a3d",
    "#e03131": "#ff5a5a", "#c92a2a": "#ff4d5e",
}

_TAG = re.compile(r"<(\w+)([^<>]*?)(/?)>")
_ATTR = re.compile(r'\b(fill|stroke)="(#[0-9a-fA-F]{3,6})"')
_PAPER = re.compile(r'<rect width="100%" height="100%" fill="#(?:fff|ffffff)"/>')


def _rgb(colour):
    h = colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def _mix(a, b, t):
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _fallback(tag, kind, colour):
    """Colours not in the tables, by brightness: pale card fills become dark
    glass in their own hue, dark text becomes light, dark lines glow cyan."""
    rgb = _rgb(colour)
    lum = _lum(rgb)
    if tag == "text":
        return TEXT_HI if lum < 0.45 else colour
    if kind == "fill":
        if lum <= 0.75:
            return colour
        # a pale tint: find its hue again, then make a dark glass of it
        d = [255 - v for v in rgb]
        k = 200 / max(1, max(d))
        vivid = tuple(max(0, min(255, round(255 - v * k))) for v in d) if max(d) > 6 else _rgb(GLASS)
        return _mix(vivid, _rgb(BG), 0.8)
    return CYAN if lum < 0.2 else colour


def _swap(tag, attrs):
    def one(m):
        kind, colour = m.group(1), m.group(2).lower()
        table = TEXT if tag == "text" else (SHAPE_FILL if kind == "fill" else STROKE)
        new = table.get(colour) or BRIGHTER.get(colour) or _fallback(tag, kind, colour)
        return f'{kind}="{new}"'
    return _ATTR.sub(one, attrs)


def theme(svg: str) -> str:
    """The SVG recoloured for the HUD (the paper background removed, so the
    page's grid shows through)."""
    if not svg:
        return svg
    svg = _PAPER.sub("", svg, count=1)
    return _TAG.sub(lambda m: f"<{m.group(1)}{_swap(m.group(1), m.group(2))}{m.group(3)}>", svg)
