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

IS_WINDOWS = sys.platform == "win32"
# On Windows this colour is see-through, so the orb's dots float straight on
# the desktop with nothing behind them. Elsewhere it shows as a dark background.
KEY = "#010203" if IS_WINDOWS else "#0b0f14"
PANEL, PANEL_EDGE = "#0f141a", "#1c2631"
TEXT, MUTED = "#f2f6fa", "#b4c0cc"
YOU_TEXT = "#cfd9e3"
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
FPS = 30

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


class Orb:
    """A small sphere of particles with one thin ring, on a Canvas."""

    def __init__(self, canvas, cx, cy, radius):
        self.c, self.cx, self.cy, self.r = canvas, cx, cy, radius
        self.colour = SILVER
        self.colours = {}    # status -> colour chosen in Settings
        self.energy = 0.0
        self.angle = 0.0
        self.t0 = time.perf_counter()
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

    def frame(self, status, level=0.0):
        _, target, spin, swirl, ripple = STATES.get(status, STATES["idle"])
        target = self.colours.get(status, target)
        t = time.perf_counter() - self.t0
        self.colour = _mix(self.colour, target, 0.1)
        self.energy += (level - self.energy) * (0.5 if level > self.energy else 0.15)
        energy = self.energy
        self.angle += spin / FPS * (1 + energy)
        c, cx, cy, r = self.c, self.cx, self.cy, self.r
        breathe = 1 + 0.02 * math.sin(t * 1.3) + 0.1 * energy

        busy = status in ACTIVE
        c.itemconfigure(self.ring, start=(90 - math.degrees(self.angle) * 1.5) % 360,
                        extent=300 if busy else 359,
                        outline=_hex(_mix((95, 105, 115), self.colour, 0.75 if busy else 0.3)))

        cos_t, sin_t = math.cos(0.35), math.sin(0.35)
        amp = ripple + energy * 0.28
        # No backing disc any more, so the dots must stand out on any wallpaper:
        # far-side dots are a dimmer shade of the colour (not near-black), and
        # each dot gets a thin darker rim so it still shows on a white window.
        dim = _mix(self.colour, (70, 78, 86), 0.55)
        for (x, y, z, phase, speed), dot in zip(self.points, self.dots):
            a = (self.angle * speed if swirl else self.angle) + swirl * y * 1.5 * math.sin(t * 0.7)
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
        self.canvas = self.entry = self.hit = None
        self.settings_window = None

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
        self._build()
        self.set_status("starting")
        self.set_expanded(False, force=True)
        ui_events.on(lambda kind, text: self.events.put((kind, text)))
        root.after(1000 // FPS, self.tick)

    # ----- settings -----
    def load_settings(self):
        from brain import settings
        self.prefs = settings.app()
        self.size = settings.ORB_SIZES.get(self.prefs["orb_size"], ORB)
        self.colours = {name: _rgb(self.prefs[f"{key}_color"], STATES[name][1])
                        for name, key in (("idle", "orb"), ("listening", "listening"),
                                          ("thinking", "thinking"), ("speaking", "speaking"))}
        self.text_colour = self.prefs["text_color"]

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
        for w in (self.canvas, self.entry, self.hit):
            if w is not None:
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        self.canvas = self.entry = self.hit = None
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
        for item in (self.status_item, self.you_item, self.jarvis_item, self.hint_item):
            c.addtag_withtag("panel", item)
            for s in self.shadows[item]:
                c.addtag_withtag("panel", s)
        c.tag_bind("panel", "<Button-1>", lambda e: self.open_typing() if self.prefs["show_text_box"] else None)
        self.panel_items += [self.status_item, self.you_item, self.jarvis_item, self.entry_item, self.hint_item]
        self.panel_items += [s for group in self.shadows.values() for s in group]
        # Orb: just the particles and ring, no disc behind them
        self.orb = Orb(c, self.ox, self.oy, S * 0.28)
        self.orb.colours = self.colours
        for item in [self.orb.ring] + self.orb.dots:
            c.addtag_withtag("orb", item)
        c.tag_bind("orb", "<ButtonPress-1>", self._press)
        c.tag_bind("orb", "<B1-Motion>", self._move)
        c.tag_bind("orb", "<ButtonRelease-1>", self._release)
        c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        c.bind("<Button-2>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))  # macOS right-click
        self.hit = self._hit_area() if IS_WINDOWS else None

    OUTLINE = ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1))

    def _text(self, x, y, **kw):
        """A text item with a thin black outline: copies of the same text, 1px
        around it, drawn underneath and kept in step with it."""
        group = [self.canvas.create_text(x + dx, y + dy, **{**kw, "fill": SHADOW}) for dx, dy in self.OUTLINE]
        item = self.canvas.create_text(x, y, **kw)
        self.shadows[item] = group
        return item

    def set_text(self, item, **kw):
        self.canvas.itemconfigure(item, **kw)
        kw.pop("fill", None)
        if kw:
            for s in self.shadows[item]:
                self.canvas.itemconfigure(s, **kw)

    def move_text(self, item, x, y):
        self.canvas.coords(item, x, y)
        for s, (dx, dy) in zip(self.shadows[item], self.OUTLINE):
            self.canvas.coords(s, x + dx, y + dy)

    def _hit_area(self):
        """See-through pixels on Windows also let clicks fall through to the
        window underneath, so without a backing disc only the tiny dots would be
        clickable. This almost invisible square (1% opacity) under the orb
        catches clicks and drags for it instead."""
        try:
            hit = tk.Toplevel(self.root)
            hit.overrideredirect(True)
            hit.attributes("-topmost", True)
            hit.attributes("-alpha", 0.01)
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
        for item in self.panel_items:
            show = on
            if item == self.entry_item:
                show = on and self.typing   # the text box only appears when you click to type
                # Some Tk builds (seen on Windows) ignore "hidden" for embedded
                # widgets, so also move the box far outside the canvas.
                self.canvas.coords(item, self.entry_xy if show else (-5000, -5000))
            elif item == self.hint_item or item in self.shadows.get(self.hint_item, ()):
                show = on and not self.typing and self.prefs["show_text_box"]
            self.canvas.itemconfigure(item, state="normal" if show else "hidden")
        self._place()

    def _place(self):
        # Keep the orb on screen whatever happens (e.g. a different screen size).
        S = self.size
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.right = min(max(self.right, S), sw)
        self.top = min(max(self.top, 0), max(0, sh - S))
        if FIXED_SIZE or self.expanded:
            # On Windows the window never changes size: the panel area is
            # see-through and clicks pass through it, so opening the panel can't move the orb.
            w, h = self.W, self.H
            x0, y0 = 0, 0
        else:
            # Collapsed elsewhere: a window just the orb's size, scrolled to it.
            w, h = S, S
            x0, y0 = self.ox - S / 2, self.oy - S / 2
        self.canvas.configure(width=w, height=h, scrollregion=(x0, y0, x0 + w, y0 + h))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        # where the canvas's (x0, y0) goes so the orb lands at (right - S, top)
        left = self.right - S - (self.ox - S / 2 - x0)
        top = self.top - (self.oy - S / 2 - y0)
        self.root.geometry(f"{w}x{h}+{int(left)}+{int(top)}")
        if getattr(self, "hit", None):
            self.hit.geometry(f"{S}x{S}+{int(self.right - S)}+{int(self.top)}")
            self.root.lift()

    def to_corner(self):
        self.right, self.top = self._corner()
        self._save_position(None)
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
        self.drag = (e.x_root, e.y_root, self.right, self.top, False)

    def _move(self, e):
        if not self.drag:
            return
        x0, y0, r0, b0, moved = self.drag
        dx, dy = e.x_root - x0, e.y_root - y0
        if moved or abs(dx) + abs(dy) > 5:
            self.drag = (x0, y0, r0, b0, True)
            self.right, self.top = r0 + dx, b0 + dy
            self._place()

    def _release(self, e):
        moved = self.drag and self.drag[4]
        self.drag = None
        if not moved:
            self.talk()
            return
        self._save_position([int(self.right), int(self.top)])  # he's there next time too
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

        if self.status in ACTIVE or (self.typing and (self.entry.get() or self.root.focus_get() == self.entry)):
            self.last_activity = time.time()
        self.set_expanded(time.time() - self.last_activity < self.prefs["panel_seconds"])
        self.root.after(1000 // FPS, self.tick)

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
        self.set_text(self.status_item, text=label.upper(), fill=_hex(colour))
        if status in ACTIVE:
            self.last_activity = time.time()


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
