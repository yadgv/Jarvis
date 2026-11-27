"""Jarvis's own pointer: a glowing arrow that glides across the screen to show
him things, with a ring around what it points at and a short label.

It never touches his real mouse: it's a see-through, click-through window on
top of everything, run as its own small process (skills/pointer.py starts it
and sends one JSON command per line on stdin):

    {"cmd": "point", "x": 100, "y": 200, "w": 80, "h": 30, "label": "Save", "hold": 10}
    {"cmd": "hide"}
    {"cmd": "ping"}      (answers "pong" on stdout)
    {"cmd": "quit"}

Everything it prints goes to Jarvis's log as "[pointer] window: ...".

Coordinates are real screen pixels (this process is DPI aware, like UI
Automation and the OCR boxes). Run it alone to see a demo: python pointer_overlay.py --demo
"""
import json
import math
import queue
import re
import sys
import threading
import time

try:
    import tkinter as tk
except ImportError:   # only the drawing needs it (tests import the maths)
    tk = None

IS_WINDOWS = sys.platform == "win32"
KEY = "#010203"            # see-through colour
CYAN, DEEP, HALO = "#4fe3ff", "#118fbf", "#0a3d57"     # bright edge, glow, outer haze
INK, PANEL = "#eafcff", "#07131d"                       # label text and its pill
GLOW, DARK, WHITE = DEEP, PANEL, INK                    # older names
FPS = 60
# An outlined navigation arrow pointing up-left (a triangle with a notch in its tail), drawn as a thick
# glowing line with nothing inside, about 30 px at 100% scaling (tip at 0, 0).
ARROW = [(0, 0), (29, 12), (16, 16), (12, 29)]
TRAIL_SECS = 0.22


def say(text):
    print(text, flush=True)


def _dpi_aware():
    """How it became DPI aware (for the log)."""
    if not IS_WINDOWS:
        return "not Windows"
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            return "system"
        except Exception as e:
            return f"none ({e})"


def _virtual_screen(root):
    """(left, top, width, height) of all monitors together."""
    if IS_WINDOWS:
        import ctypes
        m = ctypes.windll.user32.GetSystemMetrics
        return m(76), m(77), m(78), m(79)
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def _click_through(root):
    """Windows: clicks and the keyboard go straight through to the apps underneath."""
    if not IS_WINDOWS:
        return
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
    GWL_EXSTYLE = -20
    LAYERED, TRANSPARENT, TOOLWINDOW, NOACTIVATE = 0x80000, 0x20, 0x80, 0x8000000
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE)
    return hwnd


def _to_front(hwnd):
    """Windows: above every other window (even ones that are 'always on top' too), without taking focus."""
    if not (IS_WINDOWS and hwnd):
        return
    import ctypes
    HWND_TOPMOST, NOSIZE, NOMOVE, NOACTIVATE, SHOW = -1, 0x1, 0x2, 0x10, 0x40
    ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, NOSIZE | NOMOVE | NOACTIVATE | SHOW)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def glide_path(start, end, t):
    """Where the pointer is at time t (0..1) on a gentle arc from start to end."""
    (x0, y0), (x1, y1) = start, end
    k = ease(t)
    dx, dy = x1 - x0, y1 - y0
    bend = min(120.0, math.hypot(dx, dy) * 0.18) * math.sin(math.pi * k)
    n = math.hypot(dx, dy) or 1.0
    return x0 + dx * k - dy / n * bend, y0 + dy * k + dx / n * bend


def tip_for(x, y, w, h):
    """The arrow's tip lands inside the target, towards its lower right, so the arrow hangs off the corner."""
    return x + w * 0.72, y + h * 0.7


def mix(a, b, k):
    """A colour k (0..1) of the way from a to b: Tk can't do see-through items, so fading is done by colour."""
    k = max(0.0, min(1.0, k))
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * k):02x}" for x, y in zip(pa, pb))


def perimeter(x1, y1, x2, y2, frac):
    """The points along a box's edge from its top-left corner, clockwise, as far as frac (0..1) of the way."""
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    total = 2 * ((x2 - x1) + (y2 - y1)) or 1.0
    left, pts = max(0.0, min(1.0, frac)) * total, [corners[0]]
    for (ax, ay), (bx, by) in zip(corners, corners[1:]):
        seg = math.hypot(bx - ax, by - ay)
        if left >= seg:
            pts.append((bx, by))
            left -= seg
            continue
        if seg:
            k = left / seg
            pts.append((ax + (bx - ax) * k, ay + (by - ay) * k))
        break
    return pts


def rounded(x1, y1, x2, y2, r):
    """Points for a rounded box (a Tk polygon with smooth=True)."""
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
            x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def palette(base):
    """The pointer's colours from one colour (Jarvis's orb colour): bright edge, glow, outer haze."""
    return mix(base, "#ffffff", 0.18), mix(base, "#000000", 0.42), mix(base, "#000000", 0.72)


def toward(now, goal, k):
    """A colour moved k of the way to another (for smooth colour changes)."""
    return mix(now, goal, k)


def _scale():
    """1.0 at 100% Windows scaling, 1.5 at 150%..."""
    if IS_WINDOWS:
        try:
            import ctypes
            return max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96)
        except Exception:
            pass
    return 1.0


class Pointer:
    def __init__(self, root, commands):
        self.root, self.commands = root, commands
        self.ox, self.oy, sw, sh = _virtual_screen(root)
        self.size = (sw, sh)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=KEY)
        if IS_WINDOWS:
            root.attributes("-transparentcolor", KEY)
        root.geometry(f"{sw}x{sh}+{self.ox}+{self.oy}")
        self.c = tk.Canvas(root, width=sw, height=sh, bg=KEY, highlightthickness=0, bd=0)
        self.c.pack()
        root.update_idletasks()
        self.hwnd = _click_through(root)
        self.drawn = False
        self.s = _scale()
        self.pos = (sw - 80.0, 60.0)       # starts near the orb's corner
        self.trail = []                    # [(x, y, time)] behind it while it glides
        self.colour = self.colour_to = CYAN    # follows Jarvis's orb colour ({"cmd": "colour"})
        self.cyan, self.deep, self.halo = palette(CYAN)
        self.arrived_at = 0.0
        self.move = None                   # (start, end, t0, secs)
        self.target = None                 # (x, y, w, h, label) in canvas coords
        self.shown_at = 0.0
        self.hide_at = 0.0
        self.visible = False
        root.withdraw()
        root.after(1000 // FPS, self.tick)

    # ----- commands -----
    def handle(self, cmd):
        kind = cmd.get("cmd")
        if kind == "quit":
            self.root.destroy()
            sys.exit(0)
        if kind == "ping":
            say("pong")
            return
        if kind == "colour":
            self._set_colour(cmd.get("hex"))
            return
        if kind == "hide":
            self.hide_at = time.time()
            return
        if kind != "point":
            return
        x, y = float(cmd["x"]) - self.ox, float(cmd["y"]) - self.oy
        w, h = max(4.0, float(cmd.get("w") or 4)), max(4.0, float(cmd.get("h") or 4))
        self.target = (x, y, w, h, str(cmd.get("label") or "")[:60])
        if cmd.get("colour"):
            self._set_colour(cmd["colour"], now=not self.visible)
        end = tip_for(x, y, w, h)
        if not self.visible:
            self.root.attributes("-alpha", 0.0)
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.update_idletasks()
            self.hwnd = _click_through(self.root) or self.hwnd   # showing again can drop the click-through style
            self.visible = True
            self.shown_at = time.time()
        _to_front(self.hwnd)
        self.drawn = False
        say(f"pointing at {int(x)},{int(y)} {int(w)}x{int(h)} (on a {self.size[0]}x{self.size[1]} window) "
            f"label {self.target[4]!r}")
        dist = math.hypot(end[0] - self.pos[0], end[1] - self.pos[1])
        self.move = (self.pos, end, time.time(), max(0.45, min(0.9, dist / 1400)))
        self.trail = []
        self.hide_at = time.time() + float(cmd.get("hold") or 10)

    def _set_colour(self, hexcolour, now=False):
        if not (isinstance(hexcolour, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", hexcolour)):
            return
        self.colour_to = hexcolour.lower()
        if now:
            self.colour = self.colour_to
            self.cyan, self.deep, self.halo = palette(self.colour)

    # ----- drawing -----
    def tick(self):
        start = time.perf_counter()
        try:
            self._tick()
        except SystemExit:
            raise
        except Exception:
            import traceback
            say("error: " + traceback.format_exc().strip().replace("\n", " | "))
        spent = (time.perf_counter() - start) * 1000
        frame = 1000 / FPS if self.visible else 50      # resting: just listen for commands
        self.root.after(max(1, int(frame - spent)), self.tick)

    def _tick(self):
        try:
            while True:
                self.handle(self.commands.get_nowait())
        except queue.Empty:
            pass
        if not self.visible:
            self.colour = self.colour_to
            self.cyan, self.deep, self.halo = palette(self.colour)
            return
        now = time.time()
        if self.colour != self.colour_to:                      # glide to Jarvis's new colour
            self.colour = toward(self.colour, self.colour_to, 0.12)
            if self.colour == toward(self.colour, self.colour_to, 0.12):
                self.colour = self.colour_to
            self.cyan, self.deep, self.halo = palette(self.colour)
        if self.move:
            start, end, t0, secs = self.move
            t = (now - t0) / secs
            self.pos = glide_path(start, end, t)
            self.trail.append((self.pos[0], self.pos[1], now))
            if t >= 1:
                self.pos, self.move, self.arrived_at = end, None, now
        self.trail = [p for p in self.trail if now - p[2] < TRAIL_SECS]
        alpha = ease((now - self.shown_at) / 0.18)                      # fades in...
        if now >= self.hide_at:
            alpha = min(alpha, 1 - ease((now - self.hide_at) / 0.35))   # ...and softly out
            if alpha <= 0:
                self.c.delete("all")
                self.root.withdraw()
                self.visible, self.target, self.trail = False, None, []
                say("hidden")
                return
        self.root.attributes("-alpha", max(0.0, min(1.0, alpha)))
        arrived = self.move is None
        self.draw(now, arrived)
        if arrived and not self.drawn:
            self.drawn = True
            say(f"arrived and drawn at {int(self.pos[0])},{int(self.pos[1])}")

    def draw(self, now, arrived):
        c, S = self.c, self.s
        c.delete("all")
        since = now - self.arrived_at if arrived else -1.0
        if self.target and arrived:
            self._ring(now, since)
        self._trail(now)
        px, py = self.pos
        if arrived:
            py += math.sin(now * 2.6) * 1.2 * S                 # a gentle hover once it's there
            ripple = since / 0.5
            if 0 <= ripple < 1:                                 # a soft "tap" where it lands
                r = (4 + 20 * ease(ripple)) * S
                c.create_oval(px - r, py - r, px + r, py + r, outline=mix(self.cyan, self.deep, ripple), width=max(1, 2 * S))
        self._arrow(px, py)

    def _arrow(self, px, py):
        """A hollow arrow: thick glowing outline, nothing inside (like a map's navigation arrow)."""
        c, S = self.c, self.s
        pts = [v for ax, ay in ARROW for v in (px + ax * S, py + ay * S)]
        for colour, width in ((self.halo, 6.0), (self.deep, 4.2), (self.cyan, 2.4)):
            c.create_polygon(pts, fill="", outline=colour, width=width * S, joinstyle="miter")

    def _trail(self, now):
        c, S, pts = self.c, self.s, self.trail
        for (x0, y0, t0), (x1, y1, t1) in zip(pts, pts[1:]):
            k = 1 - (now - t1) / TRAIL_SECS                     # 1 = fresh, 0 = gone
            c.create_line(x0, y0, x1, y1, fill=mix(self.halo, self.cyan, k * 0.9), width=max(1, (1 + 3 * k) * S),
                          capstyle="round")

    def _ring(self, now, since):
        c, S = self.c, self.s
        x, y, w, h, label = self.target
        p = ease(since / 0.35)                                  # 0..1 as it settles in
        pad = 6 * S + (1 - p) * 16 * S
        x1, y1, x2, y2 = x - pad, y - pad, x + w + pad, y + h + pad
        # a thin outline that draws itself around the thing, clockwise
        edge = perimeter(x1, y1, x2, y2, ease((since - 0.08) / 0.45))
        if len(edge) > 1:
            c.create_line(*[v for pt in edge for v in pt], fill=mix(self.halo, self.deep, p), width=max(1, S))
        # corner brackets that close in on it, then breathe
        breathe = math.sin(now * 3.2) * 1.4 * S * p
        L = min(14 * S, (x2 - x1) / 3, (y2 - y1) / 2.2)
        colour, wid = mix(self.halo, self.cyan, p), max(2, 2 * S)
        for cx, cy, sx, sy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x2, y2, -1, -1), (x1, y2, 1, -1)):
            cx, cy = cx - sx * breathe, cy - sy * breathe
            c.create_line(cx, cy + sy * L, cx, cy, cx + sx * L, cy, fill=colour, width=wid, capstyle="round",
                          joinstyle="round")
        # a little light running round the edge
        if since > 0.5:
            run = perimeter(x1, y1, x2, y2, (since * 0.45) % 1.0)[-1]
            r = 2.2 * S
            c.create_oval(run[0] - r - S, run[1] - r - S, run[0] + r + S, run[1] + r + S, fill=self.halo, outline="")
            c.create_oval(run[0] - r, run[1] - r, run[0] + r, run[1] + r, fill=self.cyan, outline="")
        if label:
            self._label(label, x1, y1, x2, y2, since)

    def _label(self, label, x1, y1, x2, y2, since):
        c, S = self.c, self.s
        k = ease((since - 0.18) / 0.3)
        if k <= 0:
            return
        font = ("Segoe UI Semibold", 10)
        text = c.create_text(0, 0, text=label, anchor="w", font=font, fill=mix(PANEL, INK, k))
        tx1, ty1, tx2, ty2 = c.bbox(text)
        tw, th = tx2 - tx1, ty2 - ty1
        gap, padx, pady = 12 * S, 9 * S, 4 * S
        cy = (y1 + y2) / 2
        right = x2 + gap + tw + 2 * padx < c.winfo_width() - 4
        slide = (1 - k) * 10 * S
        bx1 = (x2 + gap + slide) if right else (x1 - gap - tw - 2 * padx - slide)
        bx2, by1, by2 = bx1 + tw + 2 * padx, cy - th / 2 - pady, cy + th / 2 + pady
        edge_x = x2 if right else x1
        c.create_line(edge_x, cy, bx1 if right else bx2, cy, fill=mix(PANEL, self.deep, k), width=max(1, S))
        pill = c.create_polygon(rounded(bx1, by1, bx2, by2, (by2 - by1) / 2), smooth=True,
                                fill=PANEL, outline=mix(PANEL, self.deep, k), width=max(1, S))
        dot = c.create_oval(bx1 + 4 * S, cy - 2 * S, bx1 + 8 * S, cy + 2 * S, fill=mix(PANEL, self.cyan, k), outline="")
        c.coords(text, bx1 + padx + 2 * S, cy)
        c.tag_raise(pill)
        c.tag_raise(dot)
        c.tag_raise(text)


def _read_stdin(q):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            q.put(json.loads(line))
        except ValueError:
            continue
    q.put({"cmd": "quit"})   # Jarvis closed: go too


def main():
    if tk is None:
        say("error: tkinter isn't installed, so the pointer can't be drawn")
        sys.exit(1)
    dpi = _dpi_aware()
    q = queue.Queue()
    root = tk.Tk()
    root.title("Jarvis pointer")
    p = Pointer(root, q)
    say(f"ready: covers {p.size[0]}x{p.size[1]} from {p.ox},{p.oy}; DPI aware: {dpi}; Tk {tk.TkVersion}")
    if "--demo" in sys.argv:
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        for i, (x, y, label) in enumerate([(sw * 0.2, sh * 0.3, "Here"), (sw * 0.6, sh * 0.6, "Then here")]):
            root.after(500 + i * 2500, lambda x=x, y=y, l=label: q.put(
                {"cmd": "point", "x": x, "y": y, "w": 120, "h": 36, "label": l, "hold": 3}))
        root.after(7000, root.destroy)
    else:
        threading.Thread(target=_read_stdin, args=(q,), daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
