"""Jarvis's own pointer: a glowing arrow that glides across the screen to show
him things, with a ring around what it points at and a short label.

It never touches his real mouse: it's a see-through, click-through window on
top of everything, run as its own small process (skills/pointer.py starts it
and sends one JSON command per line on stdin):

    {"cmd": "point", "x": 100, "y": 200, "w": 80, "h": 30, "label": "Save", "hold": 10}
    {"cmd": "hide"}
    {"cmd": "quit"}

Coordinates are real screen pixels (this process is DPI aware, like UI
Automation and the OCR boxes). Run it alone to see a demo: python pointer_overlay.py --demo
"""
import json
import math
import queue
import sys
import threading
import time

try:
    import tkinter as tk
except ImportError:   # only the drawing needs it (tests import the maths)
    tk = None

IS_WINDOWS = sys.platform == "win32"
KEY = "#010203"            # see-through colour
CYAN, GLOW, DARK, WHITE = "#38d6ff", "#1478a8", "#0b1622", "#eaf8ff"
FPS = 60
ARROW = [(0, 0), (0, 36), (10, 28), (17, 43), (24, 40), (17, 25), (29, 25)]   # tip at (0, 0)


def _dpi_aware():
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


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
    """The arrow's tip lands just inside the target, a little below and right of its centre-left."""
    return x + min(w * 0.5, max(12, w * 0.3)), y + h * 0.62


class Pointer:
    def __init__(self, root, commands):
        self.root, self.commands = root, commands
        self.ox, self.oy, sw, sh = _virtual_screen(root)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=KEY)
        if IS_WINDOWS:
            root.attributes("-transparentcolor", KEY)
        root.geometry(f"{sw}x{sh}+{self.ox}+{self.oy}")
        self.c = tk.Canvas(root, width=sw, height=sh, bg=KEY, highlightthickness=0, bd=0)
        self.c.pack()
        root.update_idletasks()
        _click_through(root)
        self.pos = (sw - 80.0, 60.0)       # starts near the orb's corner
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
        if kind == "hide":
            self.hide_at = time.time()
            return
        if kind != "point":
            return
        x, y = float(cmd["x"]) - self.ox, float(cmd["y"]) - self.oy
        w, h = max(4.0, float(cmd.get("w") or 4)), max(4.0, float(cmd.get("h") or 4))
        self.target = (x, y, w, h, str(cmd.get("label") or "")[:60])
        end = tip_for(x, y, w, h)
        if not self.visible:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 1.0)
            self.visible = True
        dist = math.hypot(end[0] - self.pos[0], end[1] - self.pos[1])
        self.move = (self.pos, end, time.time(), max(0.5, min(1.1, dist / 1000)))
        self.shown_at = time.time()
        self.hide_at = time.time() + float(cmd.get("hold") or 10)

    # ----- drawing -----
    def tick(self):
        try:
            while True:
                self.handle(self.commands.get_nowait())
        except queue.Empty:
            pass
        now = time.time()
        if self.visible:
            arrived = True
            if self.move:
                start, end, t0, secs = self.move
                t = (now - t0) / secs
                self.pos = glide_path(start, end, t)
                arrived = t >= 1
                if arrived:
                    self.pos, self.move = end, None
            fade = 1.0
            if now >= self.hide_at:
                fade = max(0.0, 1 - (now - self.hide_at) / 0.4)
                if fade <= 0:
                    self.root.withdraw()
                    self.visible, self.target = False, None
            if self.visible:
                self.root.attributes("-alpha", fade)
                self.draw(now, arrived)
        self.root.after(1000 // FPS, self.tick)

    def draw(self, now, arrived):
        c = self.c
        c.delete("all")
        if self.target and arrived:
            x, y, w, h, label = self.target
            pad = 8
            since = now - (self.move[2] + self.move[3] if self.move else self.shown_at)
            pulse = 0.5 + 0.5 * math.sin(now * 5)
            grow = 6 * max(0.0, 1 - since * 2) if since >= 0 else 6
            x1, y1, x2, y2 = x - pad - grow, y - pad - grow, x + w + pad + grow, y + h + pad + grow
            c.create_rectangle(x1 - 3, y1 - 3, x2 + 3, y2 + 3, outline=GLOW, width=2)
            c.create_rectangle(x1, y1, x2, y2, outline=CYAN, width=3 + 2 * pulse)
            if label:
                lx, ly = x2 + 14, y1
                if lx + 12 + 8 * len(label) > c.winfo_width():
                    lx = max(4, x1 - 24 - 8 * len(label))
                text = c.create_text(lx + 12, ly + 13, text=label, fill=WHITE, anchor="w",
                                     font=("Segoe UI", 12, "bold"))
                bx1, by1, bx2, by2 = c.bbox(text)
                box = c.create_rectangle(bx1 - 10, by1 - 6, bx2 + 10, by2 + 6, fill=DARK, outline=CYAN, width=2)
                c.tag_lower(box, text)
        px, py = self.pos
        # The arrow: a dark shadow, a cyan glow outline, then the bright body.
        pts = [(px + ax, py + ay) for ax, ay in ARROW]
        c.create_polygon([(x + 2, y + 3) for x, y in pts], fill=DARK, outline=DARK)
        c.create_polygon(pts, fill=CYAN, outline=GLOW, width=3)
        c.create_polygon(pts, fill=CYAN, outline=WHITE, width=1)


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
    _dpi_aware()
    q = queue.Queue()
    root = tk.Tk()
    root.title("Jarvis pointer")
    Pointer(root, q)
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
