"""JARVIS corner widget: a small orb of particles that sits on top of your
other windows in the top-right corner of the screen.

    python gui.py          (or: python main.py --gui)

- Click the orb to talk (no wake word needed); click again while he's
  speaking to stop him. "Hey Jarvis" keeps working as usual.
- Drag the orb to move it.
- While you talk to him a panel slides out next to the orb with what you
  said, his reply and a box to type in. It tucks away again when he's done.
- Right-click the orb for: type a message, Settings (voice, colours, size,
  text box, wake word, microphone and more; saved for next time), move back
  to the corner, quit. Click the panel to open the text box; Esc closes it.

The orb is silver while standing by, green while listening, amber while
thinking and blue while speaking, and it moves with the voice.

Uses tkinter, which comes with Python on Windows and is one apt package on a
Pi (sudo apt install python3-tk). If it can't open, the reason is printed in
the terminal.
"""
import startup  # noqa: F401  (first, so its clock starts at launch)
import math
import os
import queue
import random
import sys
import threading
import time
import traceback

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on the Python install
    print("[gui] tkinter isn't available in this Python.\n"
          "      Windows: reinstall Python from python.org and tick 'tcl/tk and IDLE'.\n"
          "      Raspberry Pi: sudo apt install python3-tk")
    raise

import config
import ui_events
from orb_motion import Roamer

IS_WINDOWS = sys.platform == "win32"
# On Windows this colour is see-through, so the orb's dots float straight on
# the desktop with nothing behind them. Elsewhere it shows as a dark background.
KEY = "#010203" if IS_WINDOWS else "#0b0f14"
PANEL, PANEL_EDGE = "#0f141a", "#1c2631"
TEXT, MUTED = "#f2f6fa", "#b4c0cc"
YOU_TEXT = "#cfd9e3"
ACCENT = "#78c3ff"   # the task chip's progress bar
SHADOW = "#000000"   # behind the text; not the see-through KEY colour
# On Windows the window stays one size and the panel area is see-through;
# elsewhere (no see-through colour) it shrinks to the orb when collapsed.
FIXED_SIZE = IS_WINDOWS
SANS = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"

ORB = 128            # size of the round orb, in pixels
PANEL_W = 330        # width of the panel that slides out
PANEL_H = 190
MARGIN = (24, 24)    # distance from the right and top of the screen
COLLAPSE_AFTER = 7   # seconds of quiet before the panel tucks away
PARTICLES = 220
FPS = 60             # Settings > Reduce animations: 30, and no slides, fades or ripples
CALM_FPS = 30
PANEL_ANIM = 0.24    # seconds for the text panel to slide and fade in or out

# status -> (label, colour, spin, swirl, resting ripple)
SILVER = (205, 215, 225)
STATES = {
    "starting": ("Starting up", (120, 130, 140), 0.2, 0.0, 0.01),
    "idle": ("Standing by", SILVER, 0.2, 0.0, 0.02),
    "listening": ("Listening", (120, 235, 170), 0.4, 0.0, 0.04),
    "thinking": ("Thinking", (240, 185, 90), 1.4, 1.0, 0.05),
    "speaking": ("Speaking", (120, 195, 255), 0.45, 0.0, 0.04),
    "off": ("Off", (230, 95, 110), 0.03, 0.0, 0.0),
}
ACTIVE = ("listening", "thinking", "speaking")


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _smooth(t):
    """Ease in and out: slow at both ends, so movement never starts or stops with a jerk."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Orb:
    """A small sphere of particles with one thin ring, on a Canvas."""

    def __init__(self, canvas, cx, cy, radius):
        self.c, self.cx, self.cy, self.r = canvas, cx, cy, radius
        self.colour = SILVER
        self.colours = {}    # status -> colour chosen in Settings
        self.energy = 0.0
        self.angle = 0.0
        self.t0 = self.last = time.perf_counter()
        # spin, swirl and ripple ease to each state's values instead of jumping
        self.motion = list(STATES["starting"][2:])
        # Soft glow: two faint rings just outside the dots that swell with his voice.
        self.glow = [canvas.create_oval(0, 0, 0, 0, outline=_hex(SILVER), width=w) for w in (3, 1)]
        rr = radius * 1.42
        self.ring = canvas.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=90, extent=300,
                                      style="arc", outline=_hex(SILVER), width=2)
        self.points, self.dots = [], []
        golden = math.pi * (3 - math.sqrt(5))
        for i in range(PARTICLES):
            y = 1 - 2 * (i + 0.5) / PARTICLES
            ring = math.sqrt(1 - y * y)
            theta = golden * i
            self.points.append((ring * math.cos(theta), y, ring * math.sin(theta),
                                random.uniform(0, math.tau), random.uniform(0.6, 1.4)))
            self.dots.append(canvas.create_oval(0, 0, 0, 0, outline="", fill=_hex(SILVER)))
        self.turns = [0.0] * PARTICLES   # each dot's own angle, so swirling starts and stops smoothly

    def frame(self, status, level=0.0):
        _, target, *goal = STATES.get(status, STATES["idle"])
        target = self.colours.get(status, target)
        now = time.perf_counter()
        dt, self.last = min(0.1, max(0.001, now - self.last)), now
        t = now - self.t0
        ease = lambda rate: 1 - math.exp(-rate * dt)   # the same feel at 30 or 60 frames a second
        self.colour = _mix(self.colour, target, ease(4.0))
        self.motion = [m + (g - m) * ease(3.0) for m, g in zip(self.motion, goal)]
        spin, swirl, ripple = self.motion
        self.energy += (level - self.energy) * ease(18.0 if level > self.energy else 5.0)
        energy = self.energy
        step = spin * dt * (1 + energy)
        self.angle += step
        c, cx, cy, r = self.c, self.cx, self.cy, self.r
        breathe = 1 + 0.02 * math.sin(t * 1.3) + 0.1 * energy

        busy = status in ACTIVE
        c.itemconfigure(self.ring, start=(90 - math.degrees(self.angle) * 1.5) % 360,
                        extent=300 if busy else 359,
                        outline=_hex(_mix((95, 105, 115), self.colour, 0.75 if busy else 0.3)))
        for i, g in enumerate(self.glow):
            gr = r * breathe * (1.12 + 0.1 * i + 0.22 * energy + 0.015 * math.sin(t * 2 + i))
            c.coords(g, cx - gr, cy - gr, cx + gr, cy + gr)
            c.itemconfigure(g, outline=_hex(_mix((40, 46, 54), self.colour, (0.1 + 0.55 * energy) / (1 + i))))

        cos_t, sin_t = math.cos(0.35), math.sin(0.35)
        amp = ripple + energy * 0.28
        # No backing disc any more, so the dots must stand out on any wallpaper:
        # far-side dots are a dimmer shade of the colour (not near-black), and
        # each dot gets a thin darker rim so it still shows on a white window.
        dim = _mix(self.colour, (70, 78, 86), 0.55)
        turns = self.turns
        for i, ((x, y, z, phase, speed), dot) in enumerate(zip(self.points, self.dots)):
            turns[i] += step * (1 + swirl * (speed - 1))
            a = turns[i] + swirl * y * 1.5 * math.sin(t * 0.7)
            ca, sa = math.cos(a), math.sin(a)
            x2, z2 = x * ca - z * sa, x * sa + z * ca
            y2, z3 = y * cos_t - z2 * sin_t, y * sin_t + z2 * cos_t
            wobble = 1 + amp * math.sin(t * 3 * speed + phase) + amp * 0.5 * math.sin(t * 7 + y * 6)
            depth = (z3 + 1) / 2
            persp = 1 / (1.5 - 0.5 * depth)
            px = cx + x2 * r * breathe * wobble * persp
            py = cy + y2 * r * breathe * wobble * persp
            size = 0.5 + 1.2 * depth + 0.6 * energy * depth
            colour = _mix(dim, _mix(self.colour, (255, 255, 255), 0.25 * depth), 0.2 + 0.8 * depth)
            c.coords(dot, px - size, py - size, px + size, py + size)
            c.itemconfigure(dot, fill=_hex(colour),
                            outline=_hex(_mix(colour, (10, 14, 18), 0.45)) if size > 1.5 else "")


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _rgb(hexcolour, fallback):
    try:
        h = hexcolour.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError):
        return fallback


class JarvisWidget:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.status = "starting"
        self.mic_level = 0.0
        self.expanded = None
        self.last_activity = 0.0
        self.you_text, self.jarvis_text, self.jarvis_turn_open = "", "", False
        self.drag = None
        self.typing = False
        self.canvas = self.entry = self.hit = self.orbwin = None
        self.settings_window = None
        self.reveal, self.slid = 0.0, 0.0      # panel animation: 0 hidden .. 1 shown
        self.task = None                       # {"label", "step", "total", "done", "ok", "at"}
        self.last_tick = time.perf_counter()
        self.started = time.time()

        root.overrideredirect(True)          # no title bar
        root.attributes("-topmost", True)    # stays above other windows
        root.configure(bg=KEY)
        if IS_WINDOWS:
            root.attributes("-transparentcolor", KEY)

        self.menu = tk.Menu(root, tearoff=0, bg=PANEL, fg=TEXT, activebackground=PANEL_EDGE,
                            activeforeground=TEXT, bd=0)
        self.menu.add_command(label="Type a message", command=self.open_typing)
        self.menu.add_command(label="Settings...", command=self.open_settings)
        self.menu.add_command(label="Move back to the corner", command=self.to_corner)
        if IS_WINDOWS:
            import autostart
            self.autostart = tk.BooleanVar(value=autostart.is_on())
            self.menu.add_checkbutton(label="Start with Windows", variable=self.autostart,
                                      command=lambda: print("[gui] " + autostart.set_on(self.autostart.get())))
        self.menu.add_separator()
        self.menu.add_command(label="Quit Jarvis", command=lambda: os._exit(0))

        self.load_settings()
        self.right, self.top = self._start_position()
        self.roamer = Roamer()
        self.orb_xy = (self.right - self.size, self.top)   # the orb's own window (top-left); it roams
        self._build()
        self.set_status("starting")
        self.set_expanded(False, force=True)
        ui_events.on(lambda kind, text: self.events.put((kind, text)))
        root.after(self._frame_ms(), self.tick)

    # ----- settings -----
    def load_settings(self):
        from brain import settings
        self.prefs = settings.app()
        self.size = settings.ORB_SIZES.get(self.prefs["orb_size"], ORB)
        self.colours = {name: _rgb(self.prefs[f"{key}_color"], STATES[name][1])
                        for name, key in (("idle", "orb"), ("listening", "listening"),
                                          ("thinking", "thinking"), ("speaking", "speaking"))}
        self.text_colour = self.prefs["text_color"]
        self.calm = bool(self.prefs.get("reduce_motion"))

    def _frame_ms(self):
        """60 frames a second while something moves; 30 while he stands by (the
        slow idle drift looks the same and it halves the work)."""
        busy = (self.status in ACTIVE or self.task or 0 < self.reveal < 1
                or not getattr(getattr(self, "roamer", None), "resting", True))
        return 1000 // (FPS if busy and not self.calm else CALM_FPS)

    def _corner(self, corner=None):
        """(right edge, top) of the orb in one corner of the screen."""
        corner = corner or self.prefs["corner"]
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        right = MARGIN[0] + self.size if "left" in corner else sw - MARGIN[0]
        top = sh - self.size - MARGIN[1] - 48 if "bottom" in corner else MARGIN[1]  # 48: above the taskbar
        return right, top

    def _start_position(self):
        pos = self.prefs.get("position")
        return tuple(pos) if pos else self._corner()

    def apply_settings(self, moved_corner=False):
        """After Save in the Settings window: redraw with the new look."""
        old_size = self.size
        self.load_settings()
        if moved_corner or self.size != old_size:
            if moved_corner or not self.prefs.get("position"):
                self.right, self.top = self._corner()
            self.orb_xy = (self.right - self.size, self.top)
            self.roamer.place(*self.orb_xy)
        self._rebuild()
        if self.status in STATES:
            self.set_status(self.status)

    def open_settings(self):
        if self.settings_window and self.settings_window.alive():
            self.settings_window.show()
            return
        import settings_window
        self.settings_window = settings_window.SettingsWindow(self.root, self)

    # ----- layout -----
    def _flips(self):
        """The panel opens towards the middle of the screen, so it's never cut
        off: to the right of the orb on the left half, below it on the top half."""
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        cx, cy = self.right - self.size / 2, self.top + self.size / 2
        return cx < sw / 2, cy > sh / 2

    def _rebuild(self):
        for w in (self.canvas, self.entry, self.hit, self.orbwin):
            if w is not None:
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        self.canvas = self.entry = self.hit = self.orbwin = None
        self._build()
        self.set_expanded(self.expanded, force=True)
        self._show_text(quiet=True)

    def _build(self):
        S = self.size
        self.flip_x, self.flip_y = self._flips()
        self.W, self.H = PANEL_W + S, max(S, PANEL_H)
        self.canvas = c = tk.Canvas(self.root, width=self.W, height=self.H, bg=KEY, highlightthickness=0)
        c.pack(fill="both", expand=True)
        # orb centre and the panel's top-left corner, inside the canvas
        self.ox = S / 2 if self.flip_x else PANEL_W + S / 2
        self.oy = self.H - S / 2 if self.flip_y else S / 2
        px = S if self.flip_x else 0
        py = self.H - PANEL_H if self.flip_y else 0
        self.px, self.py = px, py
        # No background: the text floats on the desktop like the orb. Each line
        # has a thin black outline so it stays readable on light windows too.
        self.panel_items = []
        self.shadows = {}
        self.fills = {}
        self.slid = 0.0
        self.status_item = self._text(px + 20, py + 18, anchor="w", font=(SANS, 9, "bold"), fill=MUTED)
        self.you_item = self._text(px + 20, py + 40, anchor="nw", width=PANEL_W - 44, font=(SANS, 9, "bold"),
                                   fill=YOU_TEXT)
        self.jarvis_item = self._text(px + 20, py + 62, anchor="nw", width=PANEL_W - 44, font=(SANS, 10, "bold"),
                                      fill=self.text_colour)
        # On Windows the KEY colour is see-through, so the text box has no fill either.
        self.entry = tk.Entry(self.root, font=(SANS, 10, "bold"), bg=KEY, fg=self.text_colour,
                              insertbackground=self.text_colour, relief="flat", highlightthickness=1,
                              highlightbackground="#6b7c8d", highlightcolor="#9fb3c6")
        self.entry.bind("<Return>", lambda e: self.send())
        self.entry.bind("<Escape>", lambda e: self.close_typing())
        self.entry_xy = (px + 18, py + PANEL_H - 20)
        self.entry_item = c.create_window(*self.entry_xy, anchor="sw", window=self.entry, width=PANEL_W - 46,
                                          height=28)
        self.hint_item = self._text(px + 20, py + PANEL_H - 24, anchor="w", text="Click here to type",
                                    font=(SANS, 8, "bold"), fill=MUTED)
        # The task chip: a spinner and a progress bar by the status line while a job runs.
        self.spinner = c.create_arc(0, 0, 0, 0, start=0, extent=110, style="arc", width=2, outline=MUTED,
                                    state="hidden")
        self.tick_mark = self._text(0, py + 18, anchor="w", text="", font=(SANS, 10, "bold"), fill="#78eba9")
        self.bar_track = c.create_line(px + 20, py + 29, px + PANEL_W - 44, py + 29, fill="#2a3440", width=3,
                                       capstyle="round", state="hidden")
        self.bar = c.create_line(px + 20, py + 29, px + 20, py + 29, fill=ACCENT, width=3, capstyle="round",
                                 state="hidden")
        self.chip_items = [self.spinner, self.bar_track, self.bar]
        for item in self.chip_items:
            c.addtag_withtag("panel", item)
        for item in (self.status_item, self.you_item, self.jarvis_item, self.hint_item, self.tick_mark):
            c.addtag_withtag("panel", item)
            for s in self.shadows[item]:
                c.addtag_withtag("panel", s)
        c.tag_bind("panel", "<Button-1>", lambda e: self.open_typing() if self.prefs["show_text_box"] else None)
        self.panel_items += [self.status_item, self.you_item, self.jarvis_item, self.entry_item, self.hint_item,
                             self.tick_mark]
        self.panel_items += [s for group in self.shadows.values() for s in group]
        # The orb has its own small window, so it can glide around the screen
        # while the text panel stays put in its corner.
        self.orbwin = ow = tk.Toplevel(self.root)
        ow.overrideredirect(True)
        ow.attributes("-topmost", True)
        ow.configure(bg=KEY)
        if IS_WINDOWS:
            ow.attributes("-transparentcolor", KEY)
        oc = self.orb_canvas = tk.Canvas(ow, width=S, height=S, bg=KEY, highlightthickness=0)
        oc.pack()
        self.orb = Orb(oc, S / 2, S / 2, S * 0.28)
        self.orb.colours = self.colours
        oc.bind("<ButtonPress-1>", self._press)
        oc.bind("<B1-Motion>", self._move)
        oc.bind("<ButtonRelease-1>", self._release)
        for w in (oc, c):
            w.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
            w.bind("<Button-2>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))  # macOS right-click
        self.hit = self._hit_area() if IS_WINDOWS else None

    OUTLINE = ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1))

    def _text(self, x, y, **kw):
        """A text item with a thin black outline: copies of the same text, 1px
        around it, drawn underneath and kept in step with it."""
        group = [self.canvas.create_text(x + dx, y + dy, **{**kw, "fill": SHADOW}) for dx, dy in self.OUTLINE]
        item = self.canvas.create_text(x, y, **kw)
        self.shadows[item] = group
        self.fills[item] = kw.get("fill", TEXT)
        return item

    def set_text(self, item, **kw):
        if "fill" in kw:
            self.fills[item] = kw["fill"]
            if self.reveal < 1:   # still fading in: the fade puts the colour on
                kw["fill"] = _hex(_mix((12, 16, 20), _rgb(kw["fill"], (242, 246, 250)), _smooth(self.reveal)))
        self.canvas.itemconfigure(item, **kw)
        kw.pop("fill", None)
        if kw:
            for s in self.shadows[item]:
                self.canvas.itemconfigure(s, **kw)

    def move_text(self, item, x, y):
        x += self.slid   # mid-slide: keep it in step with the rest of the panel
        self.canvas.coords(item, x, y)
        for s, (dx, dy) in zip(self.shadows[item], self.OUTLINE):
            self.canvas.coords(s, x + dx, y + dy)

    def _round_hit(self, S):
        """Cut the click area down to a disc the size of the orb, so even its
        1/255 shade can't show as a square around him on a light page."""
        if getattr(self, "_hit_round", None) == S or not IS_WINDOWS:
            return
        try:
            import ctypes
            self.hit.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.hit.winfo_id()) or self.hit.winfo_id()
            r = int(S * 0.34)
            c = S // 2
            region = ctypes.windll.gdi32.CreateEllipticRgn(c - r, c - r, c + r, c + r)
            ctypes.windll.user32.SetWindowRgn(hwnd, region, True)   # Windows owns the region now
            self._hit_round = S
        except Exception as e:
            print(f"[gui] couldn't round the click area: {e}")
            self._hit_round = S

    def _hit_area(self):
        """See-through pixels on Windows also let clicks fall through to the
        window underneath, so without a backing disc only the tiny dots would be
        clickable. This almost invisible square (1% opacity) under the orb
        catches clicks and drags for it instead."""
        try:
            hit = tk.Toplevel(self.root)
            hit.overrideredirect(True)
            hit.attributes("-topmost", True)
            hit.attributes("-alpha", 0.006)   # 1/255: the faintest Windows still lets clicks land on
            hit.configure(bg="black")
            hit.bind("<ButtonPress-1>", self._press)
            hit.bind("<B1-Motion>", self._move)
            hit.bind("<ButtonRelease-1>", self._release)
            hit.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
            return hit
        except tk.TclError as e:
            print(f"[gui] no click area behind the orb: {e}")
            return None

    def set_expanded(self, on, force=False):
        on = bool(on) and self.prefs["show_panel"]  # Settings: orb only, no text next to it
        if on == self.expanded and not force:
            return
        if not on:
            self.typing = False
        self.expanded = on
        if on or self.calm or self.reveal <= 0:
            self._show_items(on)
        else:
            self._show_items(True)   # stays up while it slides and fades away; tick() hides it after
        self._place()

    def _show_items(self, on):
        for item in self.panel_items:
            show = on
            if item == self.entry_item:
                show = on and self.typing and self.expanded   # the text box only appears when you click to type
                # Some Tk builds (seen on Windows) ignore "hidden" for embedded
                # widgets, so also move the box far outside the canvas.
                self.canvas.coords(item, self.entry_xy if show else (-5000, -5000))
            elif item == self.hint_item or item in self.shadows.get(self.hint_item, ()):
                show = on and not self.typing and self.prefs["show_text_box"]
            elif item == self.tick_mark or item in self.shadows.get(self.tick_mark, ()):
                show = on and bool(self.task and self.task["done"])
            self.canvas.itemconfigure(item, state="normal" if show else "hidden")
        self._show_chip(on)

    def _animate_panel(self, dt):
        """Slide the panel out from the orb and fade its text in (or back)."""
        goal = 1.0 if self.expanded else 0.0
        if self.reveal == goal:
            return
        if self.calm:
            self.reveal = goal
        elif goal > self.reveal:
            self.reveal = min(goal, self.reveal + dt / PANEL_ANIM)
        else:
            self.reveal = max(goal, self.reveal - dt / (PANEL_ANIM * 1.2))
        e = _smooth(self.reveal)
        toward_orb = -1 if self.flip_x else 1
        off = (1 - e) * 22 * toward_orb
        self.canvas.move("panel", off - self.slid, 0)
        self.slid = off
        for item, base in self.fills.items():
            if item in self.shadows:
                self.canvas.itemconfigure(item, fill=_hex(_mix((12, 16, 20), _rgb(base, (242, 246, 250)), e)))
        if self.reveal <= 0 and not self.expanded:
            self._show_items(False)
            self._place()

    def _place(self, lift=True):
        # Keep the orb on screen whatever happens (e.g. a different screen size).
        S = self.size
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.right = min(max(self.right, S), sw)
        self.top = min(max(self.top, 0), max(0, sh - S))
        if not FIXED_SIZE:
            # No see-through colour here: hide the panel's window while it's tucked away.
            if not (self.expanded or self.reveal > 0):
                if self.root.state() != "withdrawn":
                    self.root.withdraw()
                self._place_orb(lift)
                return
            if self.root.state() == "withdrawn":
                self.root.deiconify()
                self.root.after(40, lambda: self._place(lift=False))   # some window systems drop the first move
        # The panel's window stays one size; its orb slot is left empty (the orb
        # has its own window) and the see-through colour lets clicks pass through.
        w, h = self.W, self.H
        x0, y0 = 0, 0
        self.canvas.configure(width=w, height=h, scrollregion=(x0, y0, x0 + w, y0 + h))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        # where the canvas goes so its orb slot lines up with the orb's home (right - S, top)
        left = self.right - S - (self.ox - S / 2 - x0)
        top = self.top - (self.oy - S / 2 - y0)
        self.root.geometry(f"{w}x{h}+{int(left)}+{int(top)}")
        self._place_orb(lift)

    def _place_orb(self, lift=True):
        """The orb's window (and its click area) where the orb is now."""
        S = self.size
        x, y = int(self.orb_xy[0]), int(self.orb_xy[1])
        if self.orbwin is not None:
            self.orbwin.geometry(f"{S}x{S}+{x}+{y}")
        if getattr(self, "hit", None):
            self.hit.geometry(f"{S}x{S}+{x}+{y}")
            self._round_hit(S)
        if lift:
            self.root.lift()
            if self.orbwin is not None:
                self.orbwin.lift()

    def _home(self):
        """Where the orb lives (top-left): where he put it, or its corner."""
        right, top = self._start_position()
        return right - self.size, top

    def _away(self, pointer, screen) -> bool:
        """After a while with nothing going on, the orb slips off the edge of the
        screen (Settings > Hide when idle). It comes back for "Hey Jarvis", a
        reply or a task, or when the mouse touches that edge of the screen."""
        after = int(self.prefs.get("hide_after", 120) or 0)
        if after <= 0 or self.status != "idle" or self.task or self.typing:
            return False
        if pointer is not None and self.roamer.hidden(self.size, screen):
            px, py = pointer
            home_x, home_y = self._home()
            right_side = home_x + self.size / 2 >= screen[0] / 2
            at_edge = px >= screen[0] - 3 if right_side else px <= 2
            if at_edge and abs(py - (home_y + self.size / 2)) < 160:
                self.last_activity = time.time()   # he's reaching for it
                return False
        return time.time() - max(self.last_activity, self.started) > after

    def _roam(self, dt):
        """While he's active the orb wanders near the screen edges; then it glides
        home, and after a quiet while it slips off screen. The text panel stays put."""
        if self.drag:
            return
        roam = self.prefs.get("roam", True)
        active = roam and (self.status in ACTIVE or bool(self.task and not self.task["done"])) and not self.typing
        try:
            pointer = self.root.winfo_pointerxy()
        except tk.TclError:
            pointer = None
        screen = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        if self.roamer.x is None:
            self.roamer.place(*self.orb_xy)
        away = self._away(pointer, screen)
        pos = self.roamer.step(dt, active, self._home(), self.size, screen, pointer, calm=self.calm, away=away)
        if pos is not None and (int(pos[0]), int(pos[1])) != (int(self.orb_xy[0]), int(self.orb_xy[1])):
            self.orb_xy = pos
            self._place_orb(lift=False)

    def to_corner(self):
        self.right, self.top = self._corner()
        self._save_position(None)
        self.orb_xy = (self.right - self.size, self.top)
        self.roamer.place(*self.orb_xy)
        if self._flips() != (self.flip_x, self.flip_y):
            self._rebuild()
        self._place()

    def _save_position(self, pos):
        try:
            from brain import settings
            settings.save({"position": pos})
            self.prefs["position"] = pos
        except Exception as e:
            print(f"[gui] couldn't save where the orb is: {e}")

    # ----- mouse -----
    def _press(self, e):
        self.drag = (e.x_root, e.y_root, self.orb_xy[0] + self.size, self.orb_xy[1], False)

    def _move(self, e):
        if not self.drag:
            return
        x0, y0, r0, b0, moved = self.drag
        dx, dy = e.x_root - x0, e.y_root - y0
        if moved or abs(dx) + abs(dy) > 5:
            self.drag = (x0, y0, r0, b0, True)
            self.right, self.top = r0 + dx, b0 + dy
            self.orb_xy = (self.right - self.size, self.top)
            self._place()

    def _release(self, e):
        moved = self.drag and self.drag[4]
        self.drag = None
        if not moved:
            self.talk()
            return
        self._save_position([int(self.right), int(self.top)])  # he's there next time too
        self.roamer.place(*self.orb_xy)
        if self._flips() != (self.flip_x, self.flip_y):  # crossed the middle: panel to the other side
            self.root.after(10, self._rebuild)

    # ----- actions -----
    def talk(self):
        if self.status == "speaking":  # Stop
            ui_events.stop_speaking.set()
            tts = sys.modules.get("audio.tts")
            if tts:
                tts.stop()
        elif self.status == "idle":
            ui_events.inbox.put(("talk", None))
        elif self.status == "thinking":  # e.g. a long screen-control task: stop after this step
            ui_events.cancel.set()
            self.set_text(self.status_item, text="STOPPING...")

    def open_typing(self):
        if not self.prefs["show_panel"]:
            self.prefs = {**self.prefs, "show_panel": True}  # typing needs the panel for now
            self._hide_panel_after_typing = True
        self.typing = True
        self.set_expanded(True, force=True)
        self.last_activity = time.time()
        self.root.focus_force()
        self.entry.focus_set()

    def close_typing(self):
        self.entry.delete(0, "end")
        self.typing = False
        if getattr(self, "_hide_panel_after_typing", False):
            self._hide_panel_after_typing = False
            self.prefs = {**self.prefs, "show_panel": False}
        self.set_expanded(self.expanded, force=True)
        self.root.focus_set()
        self.last_activity = 0

    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        if self.status in ("idle", "starting"):
            self.entry.delete(0, "end")
            ui_events.inbox.put(("text", text))
        else:
            self.set_text(self.status_item, text="BUSY, TRY AGAIN IN A MOMENT")
        self.last_activity = time.time()

    # ----- updates -----
    def tick(self):
        now = time.perf_counter()
        dt, self.last_tick = min(0.1, now - self.last_tick), now
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "status":
                    self.set_status(text)
                elif kind == "level":
                    self.mic_level = float(text)
                elif kind == "you":
                    self.you_text, self.jarvis_text, self.jarvis_turn_open = text, "", True
                    self._show_text()
                elif kind == "jarvis":
                    if not self.jarvis_turn_open:
                        self.you_text, self.jarvis_text = "", ""
                    self.jarvis_text = (self.jarvis_text + " " + text).strip()
                    self.jarvis_turn_open = True
                    self._show_text()
                elif kind == "info":
                    self.you_text, self.jarvis_text, self.jarvis_turn_open = "", text, False
                    self._show_text()
                elif kind == "task":
                    self.start_task(text)
                elif kind == "task_done":
                    self.finish_task((text or {}).get("ok", True))
                elif kind == "click":
                    self.ripple(*text)
        except queue.Empty:
            pass

        level = 0.0
        if self.status == "speaking":
            tts = sys.modules.get("audio.tts")
            level = tts.level() if tts and hasattr(tts, "level") else 0.3 + 0.2 * math.sin(time.time() * 9)
        elif self.status == "listening":
            level = self.mic_level
            self.mic_level *= 0.85
        try:
            self.orb.frame(self.status, level)
        except tk.TclError:
            pass

        self._roam(dt)
        self._animate_panel(dt)
        self._animate_chip()
        if self.task or self.status in ACTIVE or (self.typing and (self.entry.get() or self.root.focus_get() == self.entry)):
            self.last_activity = time.time()
        self.set_expanded(time.time() - self.last_activity < self.prefs["panel_seconds"])
        self.root.after(self._frame_ms(), self.tick)

    def _show_text(self, quiet=False):
        jarvis = self.jarvis_text
        if len(jarvis) > 170:  # keep the panel small: show the end of long replies
            jarvis = "…" + jarvis[-169:].split(" ", 1)[-1]
        if not quiet:
            self.last_activity = time.time()
            self.set_expanded(True)  # hidden items have no size, so show the panel before measuring
        self.set_text(self.you_item, text=f"You: {self.you_text}" if self.you_text else "")
        self.set_text(self.jarvis_item, text=jarvis)
        _, y1, _, y2 = self.canvas.bbox(self.you_item) or (0, 0, 0, 0)
        self.move_text(self.jarvis_item, self.px + 20, (y2 + 6) if self.you_text else self.py + 40)

    def set_status(self, status):
        self.status = status
        if status == "listening":
            self.jarvis_turn_open = False  # the next reply replaces the old one
        label, colour, *_ = STATES.get(status, (status, SILVER, 0, 0, 0))
        colour = self.colours.get(status, colour)
        if self.task:   # the task chip has the status line; keep its words, take the colour
            self.set_text(self.status_item, fill=_hex(colour))
        else:
            self.set_text(self.status_item, text=label.upper(), fill=_hex(colour))
        if status in ACTIVE:
            self.last_activity = time.time()

    # ----- the task chip: "Opening Chrome...", "Moving files 3/20", then a tick -----
    def start_task(self, info):
        info = info if isinstance(info, dict) else {"label": str(info)}
        label = str(info.get("label") or "Working...")
        step, total = info.get("step"), info.get("total")
        fresh = not self.task or self.task["done"] or self.task["label"] != label
        self.task = {"label": label, "step": step, "total": total, "done": False, "ok": True,
                     "at": time.perf_counter() if fresh else self.task["at"],
                     "shown": 0.0 if fresh else self.task.get("shown", 0.0)}
        text = label.rstrip(".").rstrip() + (f"  {step}/{total}" if step and total else "...")
        self.set_text(self.status_item, text=text.upper())
        self.last_activity = time.time()
        self.set_expanded(True)
        self._show_chip(self.expanded)

    def finish_task(self, ok=True):
        if not self.task:
            return
        self.task.update(done=True, ok=bool(ok), at=time.perf_counter())
        self.set_text(self.tick_mark, text="\u2713" if ok else "\u2715", fill="#78eba9" if ok else "#e65f6e")
        if self.task["total"] and ok:
            self.task["step"] = self.task["total"]
            self.set_text(self.status_item, text=f"{self.task['label'].rstrip('.')}  "
                                                 f"{self.task['total']}/{self.task['total']}".upper())
        self._show_chip(self.expanded)

    def _show_chip(self, on):
        if not hasattr(self, "spinner"):
            return
        task = self.task
        spin = on and bool(task) and not task["done"]
        bar = on and bool(task) and bool(task.get("total"))
        mark = on and bool(task) and task["done"]
        self.canvas.itemconfigure(self.spinner, state="normal" if spin else "hidden")
        for item in (self.bar_track, self.bar):
            self.canvas.itemconfigure(item, state="normal" if bar else "hidden")
        for item in [self.tick_mark] + self.shadows[self.tick_mark]:
            self.canvas.itemconfigure(item, state="normal" if mark else "hidden")

    def _animate_chip(self):
        task = self.task
        if not task:
            return
        now = time.perf_counter()
        c = self.canvas
        x0, y0, x1, y1 = c.bbox(self.status_item) or (0, 0, 0, 0)
        cx, cy = x1 + 12, (y0 + y1) / 2   # just after the words
        if task["done"]:
            age = now - task["at"]
            # the tick pops: a little bigger, then settles
            size = 10 if self.calm else round(10 + 4 * math.sin(min(1.0, age / 0.35) * math.pi))
            self.set_text(self.tick_mark, font=(SANS, size, "bold"))
            self.move_text(self.tick_mark, cx - 5 - self.slid, cy)
            if age > 1.6:
                self.task = None
                self._show_chip(False)
                self.set_status(self.status)
                return
        else:
            r = 5
            c.coords(self.spinner, cx - r, cy - r, cx + r, cy + r)
            c.itemconfigure(self.spinner, start=(-(now - task["at"]) * 360) % 360, outline=ACCENT)
        if task.get("total"):
            target = min(1.0, (task.get("step") or 0) / max(1, task["total"]))
            task["shown"] += (target - task["shown"]) * (1.0 if self.calm else 0.18)   # the bar glides
            left = self.px + 20 + self.slid
            right = left + (PANEL_W - 64) * task["shown"]
            y = self.py + 29
            c.coords(self.bar_track, left, y, self.px + PANEL_W - 44 + self.slid, y)
            c.coords(self.bar, left, y, max(left + 1, right), y)

    # ----- a ripple where he clicks during PC control -----
    def ripple(self, x, y):
        if self.calm:
            return
        try:
            RippleWindow(self.root, x, y, _hex(self.colours.get("speaking", (120, 195, 255))))
        except tk.TclError as e:
            print(f"[gui] no click ripple: {e}")


class RippleWindow:
    """A ring that grows and fades where the mouse clicked. The middle is
    see-through and, on Windows, the whole window lets clicks pass through,
    so it never gets in the way of the click it shows."""
    SIZE, LIFE = 90, 0.5

    def __init__(self, root, x, y, colour):
        self.win = w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=KEY)
        if IS_WINDOWS:
            w.attributes("-transparentcolor", KEY)
        half = self.SIZE // 2
        w.geometry(f"{self.SIZE}x{self.SIZE}+{int(x) - half}+{int(y) - half}")
        self.c = tk.Canvas(w, width=self.SIZE, height=self.SIZE, bg=KEY, highlightthickness=0)
        self.c.pack()
        self.ring = self.c.create_oval(0, 0, 0, 0, outline=colour, width=3)
        self.colour = _rgb(colour, (120, 195, 255))
        self.t0 = time.perf_counter()
        if IS_WINDOWS:
            self._click_through()
        self.frame()

    def _click_through(self):
        try:
            import ctypes
            self.win.update_idletasks()
            hwnd = int(self.win.wm_frame(), 16)
            u = ctypes.windll.user32
            u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x20 | 0x80000 | 0x08000000)
        except Exception:
            pass

    def frame(self):
        t = (time.perf_counter() - self.t0) / self.LIFE
        if t >= 1:
            self.win.destroy()
            return
        e = 1 - (1 - t) ** 3   # fast out, slow stop
        r = 6 + (self.SIZE / 2 - 8) * e
        mid = self.SIZE / 2
        self.c.coords(self.ring, mid - r, mid - r, mid + r, mid + r)
        self.c.itemconfigure(self.ring, width=max(1, round(3 * (1 - t))),
                             outline=_hex(_mix(self.colour, (40, 46, 54), t)))
        if IS_WINDOWS:
            self.win.attributes("-alpha", max(0.05, 1 - t))
        self.win.after(16, self.frame)


def run_voice_loop():
    try:
        import main  # loads the speech models; the widget is already showing
        if config.LOG_FILE and not hasattr(sys.stdout, "file") and \
                getattr(sys.stdout, "name", None) != config.LOG_FILE:
            sys.stdout = main._Tee(sys.stdout, config.LOG_FILE)
            if sys.stderr is None:  # started with pythonw: send errors to the log too
                sys.stderr = sys.stdout
        main.main()
    except Exception as e:
        traceback.print_exc()
        ui_events.emit("info", f"Voice loop stopped: {e}")
    ui_events.emit("status", "off")


def start():
    ui_events.gui_active = True
    if IS_WINDOWS:
        try:  # sharp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    root.title("J.A.R.V.I.S.")
    try:
        from brain import settings
        settings.apply()  # choices saved in the Settings window
    except Exception as e:
        print(f"[gui] couldn't load the saved settings: {e}")
    JarvisWidget(root)
    root.lift()
    threading.Thread(target=run_voice_loop, daemon=True).start()
    print("[gui] Jarvis is in the top-right corner of your screen. "
          "Click him to talk, drag to move, right-click for options.")
    root.mainloop()


def launch():
    if sys.stdout is None and config.LOG_FILE:
        # Started at login with pythonw (no console): keep everything in jarvis.log.
        sys.stdout = sys.stderr = open(config.LOG_FILE, "a", encoding="utf-8", buffering=1)
    if ui_events.already_running():
        print("[gui] Jarvis is already running (look for the orb in the corner).")
        return
    print("[gui] starting the JARVIS widget...")
    try:
        start()
    except Exception:
        traceback.print_exc()
        print("\n[gui] The widget couldn't start. Please send the error above.")
        try:
            input("Press Enter to close.")
        except (EOFError, RuntimeError):  # no console (started at login with pythonw)
            pass


if __name__ == "__main__":
    launch()
