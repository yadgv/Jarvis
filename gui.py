"""JARVIS desktop window: a glowing orb of particles with a sci-fi HUD.

    python gui.py          (or: python main.py --gui)

The orb drifts slowly while Jarvis is standing by, turns green and ripples
with your voice while he listens, swirls amber while he thinks, and pulses
with his voice while he speaks. Below it: the conversation, a box to type
in, and a Talk button (no wake word needed) that turns into Stop while he's
speaking. "Hey Jarvis" keeps working as usual.

Uses tkinter, which comes with Python on Windows and is one apt package on a
Pi (sudo apt install python3-tk). If the window can't open, the reason is
printed in the terminal.
"""
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
BG, PANEL, LINE = "#03070c", "#08121b", "#12324a"
TEXT, MUTED = "#d7f3ff", "#5d7b8f"
CYAN = (64, 200, 255)
YOU, JARVIS = "#6effbe", "#7fd8ff"

# status -> (label, colour, spin speed, swirl, resting ripple)
STATES = {
    "starting": ("INITIALISING", (90, 140, 170), 0.25, 0.0, 0.02),
    "idle": ("STANDING BY", CYAN, 0.25, 0.0, 0.03),
    "listening": ("LISTENING", (110, 255, 190), 0.45, 0.0, 0.05),
    "thinking": ("PROCESSING", (255, 190, 80), 1.6, 1.0, 0.06),
    "speaking": ("SPEAKING", CYAN, 0.5, 0.0, 0.05),
    "off": ("OFFLINE", (240, 90, 110), 0.05, 0.0, 0.0),
}
PARTICLES = 340
FPS = 30


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


class Orb:
    """A sphere of small particles, drawn on a tkinter Canvas."""

    def __init__(self, canvas, cx, cy, radius):
        self.c, self.cx, self.cy, self.r = canvas, cx, cy, radius
        self.colour = CYAN
        self.energy = 0.0
        self.angle = 0.0
        self.t0 = time.perf_counter()

        # Soft glow behind the sphere
        self.glow = []
        for i, scale in enumerate((1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.6)):
            rr = radius * scale
            self.glow.append(canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline="", fill=BG))

        # HUD rings: rotating arcs and a ring of ticks
        self.arcs = []
        for scale, extent, width in ((1.38, 70, 2), (1.52, 110, 1), (1.52, 40, 3), (1.66, 160, 1)):
            rr = radius * scale
            self.arcs.append((canvas.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=0, extent=extent,
                                                style="arc", outline=LINE, width=width), scale))
        self.ticks = []
        for i in range(72):
            a = i / 72 * math.tau
            r1, r2 = radius * 1.78, radius * (1.86 if i % 6 == 0 else 1.81)
            self.ticks.append(canvas.create_line(cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                                                 cx + r2 * math.cos(a), cy + r2 * math.sin(a), fill=LINE))

        # Particles spread evenly over a sphere (Fibonacci lattice)
        self.points, self.dots = [], []
        golden = math.pi * (3 - math.sqrt(5))
        for i in range(PARTICLES):
            y = 1 - 2 * (i + 0.5) / PARTICLES
            ring = math.sqrt(1 - y * y)
            theta = golden * i
            self.points.append((ring * math.cos(theta), y, ring * math.sin(theta),
                                random.uniform(0, math.tau), random.uniform(0.6, 1.4)))
            self.dots.append(canvas.create_oval(0, 0, 0, 0, outline="", fill=BG))

    def frame(self, status, level=0.0):
        _, target, spin, swirl, ripple = STATES.get(status, STATES["idle"])
        t = time.perf_counter() - self.t0
        self.colour = _mix(self.colour, target, 0.08)
        self.energy += (level - self.energy) * (0.5 if level > self.energy else 0.15)
        energy = self.energy
        self.angle += spin / FPS * (1 + energy)
        c, cx, cy, r = self.c, self.cx, self.cy, self.r
        breathe = 1 + 0.025 * math.sin(t * 1.3) + 0.12 * energy

        # Glow
        for i, item in enumerate(self.glow):
            strength = (0.025 + 0.018 * i) * (1 + 1.5 * energy)
            c.itemconfigure(item, fill=_hex(_mix((3, 7, 12), self.colour, min(0.6, strength))))
        # Rings
        for i, (item, scale) in enumerate(self.arcs):
            direction = 1 if i % 2 == 0 else -1
            c.itemconfigure(item, start=(math.degrees(self.angle) * direction * (1 + i * 0.4) + i * 90) % 360,
                            outline=_hex(_mix((18, 50, 74), self.colour, 0.35 + 0.4 * energy)))
        sweep = (t * 0.6 * (1 + spin)) % 1 * len(self.ticks)
        for i, item in enumerate(self.ticks):
            d = min(abs(i - sweep), len(self.ticks) - abs(i - sweep))
            c.itemconfigure(item, fill=_hex(_mix((18, 50, 74), self.colour, max(0.0, 1 - d / 8) * 0.9)))

        # Particles
        cos_t, sin_t = math.cos(0.35), math.sin(0.35)  # tilt towards the viewer
        amp = ripple + energy * 0.32
        for (x, y, z, phase, speed), dot in zip(self.points, self.dots):
            a = self.angle * speed if swirl else self.angle
            a += swirl * y * 1.5 * math.sin(t * 0.7)  # latitudes twist past each other while thinking
            ca, sa = math.cos(a), math.sin(a)
            x2, z2 = x * ca - z * sa, x * sa + z * ca
            y2, z3 = y * cos_t - z2 * sin_t, y * sin_t + z2 * cos_t
            wobble = 1 + amp * math.sin(t * 3 * speed + phase) + amp * 0.5 * math.sin(t * 7 + y * 6)
            depth = (z3 + 1) / 2  # 0 = back, 1 = front
            persp = 1 / (1.6 - 0.6 * depth)
            px = cx + x2 * r * breathe * wobble * persp
            py = cy + y2 * r * breathe * wobble * persp
            size = 0.7 + 1.9 * depth + 1.2 * energy * depth
            bright = 0.18 + 0.82 * depth
            colour = _mix((3, 7, 12), _mix(self.colour, (255, 255, 255), 0.35 * depth * depth), bright)
            c.coords(dot, px - size, py - size, px + size, py + size)
            c.itemconfigure(dot, fill=_hex(colour))


class JarvisWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.status = "starting"
        self.last_speaker = None
        self.mic_level = 0.0
        self.orb = None

        root.title("J.A.R.V.I.S.")
        root.geometry("560x820")
        root.minsize(440, 600)
        root.configure(bg=BG)
        sans = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"
        mono = "Consolas" if IS_WINDOWS else "DejaVu Sans Mono"
        self.f_body = (sans, 11)
        self.f_name = (mono, 9, "bold")
        self.f_hud = (mono, 10, "bold")

        # Header
        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=18, pady=(12, 0))
        tk.Label(top, text="J . A . R . V . I . S", font=(mono, 13, "bold"), fg=_hex(CYAN), bg=BG).pack(side="left")
        self.clock = tk.Label(top, text="", font=(mono, 10), fg=MUTED, bg=BG)
        self.clock.pack(side="right")
        tk.Frame(root, bg=LINE, height=1).pack(fill="x", padx=18, pady=(8, 0))

        # Input row (packed first from the bottom so it always keeps its space)
        row = tk.Frame(root, bg=BG)
        row.pack(side="bottom", fill="x", padx=18, pady=(6, 16))
        self.entry = tk.Entry(row, font=self.f_body, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              relief="flat", highlightthickness=1, highlightbackground=LINE,
                              highlightcolor=_hex(CYAN))
        self.entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry.bind("<Return>", lambda e: self.send())
        self._button(row, "SEND", self.send).pack(side="left", padx=(8, 0))
        self.talk_btn = self._button(row, "TALK", self.talk)
        self.talk_btn.pack(side="left", padx=(8, 0))
        root.bind("<Escape>", lambda e: self.talk() if self.status == "speaking" else None)

        # Conversation log
        box = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        box.pack(side="bottom", fill="x", padx=18, pady=(6, 0))
        self.chat = tk.Text(box, height=9, wrap="word", bg=PANEL, fg=TEXT, font=self.f_body, relief="flat",
                            padx=12, pady=8, state="disabled", cursor="arrow", spacing3=3,
                            highlightthickness=0, borderwidth=0)
        scroll = tk.Scrollbar(box, command=self.chat.yview, troughcolor=PANEL, bg=PANEL)
        self.chat.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("you_name", foreground=YOU, font=self.f_name, spacing1=8)
        self.chat.tag_configure("jarvis_name", foreground=JARVIS, font=self.f_name, spacing1=8)
        self.chat.tag_configure("info", foreground=MUTED, font=(sans, 9, "italic"), spacing1=4)

        # The orb
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._build_orb)
        self.status_text = None

        self.set_status("starting")
        self.entry.focus_set()
        ui_events.on(lambda kind, text: self.events.put((kind, text)))
        root.after(1000 // FPS, self.tick)

    def _button(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, font=self.f_hud, bg=PANEL, fg=_hex(CYAN),
                         activebackground=_hex(CYAN), activeforeground=BG, relief="flat",
                         highlightthickness=1, highlightbackground=_hex(CYAN), padx=14, pady=6, cursor="hand2",
                         disabledforeground=MUTED)

    def _build_orb(self, event):
        w, h = event.width, event.height
        if w < 50 or h < 50:
            return
        self.canvas.delete("all")
        radius = max(30, min(w, h - 40) / 2 / 1.95)
        self.orb = Orb(self.canvas, w / 2, (h - 30) / 2 + 4, radius)
        self.status_text = self.canvas.create_text(w / 2, h - 18, text="", font=self.f_hud, fill=MUTED)
        self.set_status(self.status)

    # ----- actions -----
    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        if self.status in ("idle", "starting"):
            ui_events.inbox.put(("text", text))
        else:
            self.add("info", "Jarvis is busy, try again in a moment.")
            self.entry.insert(0, text)

    def talk(self):
        if self.status == "speaking":  # Stop
            ui_events.stop_speaking.set()
            tts = sys.modules.get("audio.tts")
            if tts:
                tts.stop()
        elif self.status == "idle":
            ui_events.inbox.put(("talk", None))

    # ----- animation + updates from the voice loop -----
    def tick(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "status":
                    self.set_status(text)
                elif kind == "level":
                    self.mic_level = float(text)
                elif kind in ("you", "jarvis", "info"):
                    self.add(kind, text)
        except queue.Empty:
            pass

        level = 0.0
        if self.status == "speaking":
            tts = sys.modules.get("audio.tts")
            level = tts.level() if tts and hasattr(tts, "level") else 0.3 + 0.2 * math.sin(time.time() * 9)
        elif self.status == "listening":
            level = self.mic_level
            self.mic_level *= 0.85
        if self.orb:
            try:
                self.orb.frame(self.status, level)
            except tk.TclError:
                pass
        self.clock.configure(text=time.strftime("%H:%M:%S"))
        self.root.after(1000 // FPS, self.tick)

    def set_status(self, status):
        self.status = status
        label, colour, *_ = STATES.get(status, (status.upper(), CYAN, 0, 0, 0))
        if self.status_text:
            self.canvas.itemconfigure(self.status_text, text=f"◆  {label}  ◆", fill=_hex(colour))
        self.talk_btn.configure(text="STOP" if status == "speaking" else "TALK",
                                state="normal" if status in ("idle", "speaking") else "disabled")
        if status in ("idle", "listening"):
            self.last_speaker = None  # next Jarvis line starts a new entry

    def add(self, who, text):
        self.chat.configure(state="normal")
        if who == "info":
            self.chat.insert("end", text + "\n", "info")
        elif who == self.last_speaker == "jarvis":
            # Jarvis speaks sentence by sentence: keep one reply together.
            self.chat.delete("end-2c")
            self.chat.insert("end", " " + text + "\n")
        else:
            self.chat.insert("end", ("YOU" if who == "you" else "JARVIS") + "\n", f"{who}_name")
            self.chat.insert("end", text + "\n")
        self.last_speaker = who
        self.chat.configure(state="disabled")
        self.chat.see("end")


def run_voice_loop():
    try:
        import main  # loads the speech models; the window is already showing
        if config.LOG_FILE and not hasattr(sys.stdout, "file"):
            sys.stdout = main._Tee(sys.stdout, config.LOG_FILE)
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
    JarvisWindow(root)
    # Make sure the window shows up in front instead of behind the terminal.
    root.lift()
    root.attributes("-topmost", True)
    root.after(800, lambda: root.attributes("-topmost", False))
    root.focus_force()
    threading.Thread(target=run_voice_loop, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))  # closing the window stops Jarvis
    print("[gui] window open")
    root.mainloop()


def launch():
    print("[gui] starting the JARVIS window...")
    try:
        start()
    except Exception:
        traceback.print_exc()
        print("\n[gui] The window couldn't start. Please send the error above.")
        try:
            input("Press Enter to close.")
        except EOFError:
            pass


if __name__ == "__main__":
    launch()
