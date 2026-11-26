"""The Settings window: right-click the orb > Settings...

Everything here is saved in memory/settings.json (brain/settings.py) and is
used again the next time Jarvis starts. Save applies it straight away, except
the microphone, which is picked when Jarvis starts listening.
"""
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, ttk

import config
from brain import settings

IS_WINDOWS = sys.platform == "win32"
BG, CARD, EDGE = "#0f141a", "#151c24", "#24303c"
FG, MUTED, ACCENT = "#f2f6fa", "#9fb0c0", "#78c3ff"
SANS = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"
DEFAULT_MIC = "Default microphone"

COLOUR_LABELS = (("orb_color", "Standing by"), ("listening_color", "Listening"),
                 ("thinking_color", "Thinking"), ("speaking_color", "Speaking"), ("text_color", "Text"))


class SettingsWindow:
    def __init__(self, root, widget=None):
        self.widget = widget
        self.win = tk.Toplevel(root)
        self.win.title("Jarvis settings")
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)   # the orb is on top, so this has to be too
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        self._style()
        self.vars = {}
        self.values = {**settings.load(), **settings.app()}
        self.status = tk.StringVar(value="")

        body = tk.Frame(self.win, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(12, 4))
        left, right = tk.Frame(body, bg=BG), tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="n", padx=(0, 8))
        right.grid(row=0, column=1, sticky="n", padx=(8, 0))
        self._voice(self._card(left, "Voice"))
        self._look(self._card(left, "Look"))
        self._listening(self._card(right, "Listening"))
        self._brain(self._card(right, "Brain and extras"))

        bar = tk.Frame(self.win, bg=BG)
        bar.pack(fill="x", padx=14, pady=(4, 12))
        tk.Label(bar, textvariable=self.status, bg=BG, fg=MUTED, font=(SANS, 9)).pack(side="left")
        self._button(bar, "Save", self.save, primary=True).pack(side="right")
        self._button(bar, "Cancel", self.close).pack(side="right", padx=6)
        self._button(bar, "Reset all", self.reset).pack(side="right")
        self.show()

    # ----- building blocks -----
    def _style(self):
        st = ttk.Style(self.win)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("J.TCombobox", fieldbackground=CARD, background=CARD, foreground=FG, arrowcolor=FG,
                     bordercolor=EDGE, lightcolor=CARD, darkcolor=CARD)
        st.map("J.TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", FG)],
               selectbackground=[("readonly", CARD)], selectforeground=[("readonly", FG)])
        self.win.option_add("*TCombobox*Listbox.background", CARD)
        self.win.option_add("*TCombobox*Listbox.foreground", FG)
        self.win.option_add("*TCombobox*Listbox.selectBackground", EDGE)

    def _card(self, parent, title):
        frame = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=EDGE)
        frame.pack(fill="x", pady=(0, 10))
        tk.Label(frame, text=title.upper(), bg=CARD, fg=ACCENT, font=(SANS, 9, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 4))
        frame.columnconfigure(1, weight=1)
        frame.next_row = 1
        return frame

    def _row(self, card, label, widget_fn, note=None):
        r = card.next_row
        card.next_row += 1
        tk.Label(card, text=label, bg=CARD, fg=FG, font=(SANS, 10)).grid(row=r, column=0, sticky="w",
                                                                          padx=(12, 10), pady=4)
        w = widget_fn(card)
        w.grid(row=r, column=1, sticky="we", padx=(0, 12), pady=4)
        if note:
            tk.Label(card, text=note, bg=CARD, fg=MUTED, font=(SANS, 8)).grid(
                row=r + 1, column=0, columnspan=3, sticky="w", padx=12)
            card.next_row += 1
        return w

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0, padx=12, pady=4,
                         bg=ACCENT if primary else EDGE, fg="#0b0f14" if primary else FG,
                         activebackground="#a6d6ff" if primary else "#33414f",
                         activeforeground="#0b0f14" if primary else FG, font=(SANS, 10, "bold" if primary else ""),
                         cursor="hand2")

    def _combo(self, key, options, width=16):
        var = tk.StringVar(value=str(self.values.get(key, "")))
        self.vars[key] = var
        return lambda parent: ttk.Combobox(parent, textvariable=var, values=list(options), state="readonly",
                                           width=width, style="J.TCombobox")

    def _check(self, key, text):
        var = tk.BooleanVar(value=bool(self.values.get(key)))
        self.vars[key] = var
        return lambda parent: tk.Checkbutton(parent, text=text, variable=var, bg=CARD, fg=FG,
                                             selectcolor=BG, activebackground=CARD, activeforeground=FG,
                                             font=(SANS, 10), anchor="w", bd=0, highlightthickness=0)

    def _slider(self, key, lo, hi, step=1.0, as_type=int):
        var = tk.DoubleVar(value=float(self.values.get(key, lo)))
        self.vars[key] = var
        self.vars[key].as_type = as_type
        return lambda parent: tk.Scale(parent, variable=var, from_=lo, to=hi, resolution=step, orient="horizontal",
                                       bg=CARD, fg=FG, troughcolor=BG, highlightthickness=0, bd=0,
                                       activebackground=ACCENT, length=170, font=(SANS, 8))

    def _with_button(self, inner, text, command):
        def make(parent):
            f = tk.Frame(parent, bg=CARD)
            inner(f).pack(side="left", fill="x", expand=True)
            self._button(f, text, command).pack(side="left", padx=(6, 0))
            return f
        return make

    # ----- sections -----
    def _voice(self, card):
        online = list(getattr(config, "VOICES", {}) or {}) or ["jarvis"]
        offline = list(getattr(config, "OFFLINE_VOICES", {}) or {})
        self._row(card, "Online voice", self._with_button(self._combo("voice", online, 12), "Play",
                                                           lambda: self.preview("voice")))
        self._row(card, "Offline voice", self._with_button(self._combo("offline_voice", offline, 12), "Play",
                                                            lambda: self.preview("offline_voice")))
        self._row(card, "Speaking speed", self._slider("speed", settings.MIN_SPEED, settings.MAX_SPEED, 0.05, float))
        self._row(card, "Personality", self._combo("style", settings.STYLES))
        self._row(card, "Reply length", self._combo("length", settings.LENGTHS))
        var = tk.StringVar(value=str(self.values.get("call_me", "sir")))
        self.vars["call_me"] = var
        self._row(card, "Calls you", lambda p: tk.Entry(p, textvariable=var, bg=BG, fg=FG, insertbackground=FG,
                                                        relief="flat", font=(SANS, 10), width=18))

    def _look(self, card):
        self._row(card, "Text panel", self._check("show_panel", "Show what you said and his reply"))
        self._row(card, "Text box", self._check("show_text_box", "Show \"Click here to type\""))
        self._row(card, "Hide text after", self._slider("panel_seconds", 2, 30), note="seconds of quiet")
        self._row(card, "Orb size", self._combo("orb_size", settings.ORB_SIZES))
        corners = ("keep where I put it",) + settings.CORNERS
        self.values["corner_choice"] = "keep where I put it" if self.values.get("position") else self.values["corner"]
        self._row(card, "Position", self._combo("corner_choice", corners, 18))
        self._row(card, "Colours", self._colours)
        self._row(card, "Animations", self._check("reduce_motion", "Reduce animations"))
        self._row(card, "Move around", self._check("roam", "Glide around while he's active, then home"))

    def _colours(self, parent):
        f = tk.Frame(parent, bg=CARD)
        for i, (key, label) in enumerate(COLOUR_LABELS):
            var = tk.StringVar(value=self.values.get(key, settings.COLOURS[key]))
            self.vars[key] = var
            b = tk.Button(f, text=label, relief="flat", bd=0, font=(SANS, 8, "bold"), cursor="hand2", width=9)
            b.configure(command=lambda k=key, btn=b: self.pick_colour(k, btn))
            self._paint(b, var.get())
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="we")
        reset = tk.Button(f, text="Default", relief="flat", bd=0, font=(SANS, 8), bg=EDGE, fg=FG, cursor="hand2",
                          command=lambda: self.default_colours(f))
        reset.grid(row=1, column=2, padx=2, pady=2, sticky="we")
        return f

    def _listening(self, card):
        self._row(card, "Wake word", self._slider("wake_sensitivity", 1, 10),
                  note="higher = hears \"Hey Jarvis\" more easily (and wakes by mistake more)")
        self._row(card, "Chime", self._check("wake_chime", "Beep when he starts listening"))
        self._row(card, "Keep listening", self._slider("followup_seconds", 0, 30),
                  note="seconds of quiet before a conversation ends and \"Hey Jarvis\" is needed again (0 = off)")
        mics = [DEFAULT_MIC] + settings.microphones()
        self.values["mic"] = self.values.get("mic") or DEFAULT_MIC
        self._row(card, "Microphone", self._combo("mic", mics, 22), note="used from the next start")
        self._row(card, "Room mode", self._check("room_mode", "Hears the room before \"Hey Jarvis\""))

    def _brain(self, card):
        self._row(card, "Paid AI", self._check("ask_paid", "Ask before using Claude (costs money)"))
        self._row(card, "Offline mode", self._check("offline_mode", "Act as if the internet is down"))
        self._row(card, "Local model", self._check("local_model", "Easy questions on this PC (Ollama)"))
        self._row(card, "Music", self._check("ducking", "Turn music down while he talks"))
        self._row(card, "Phone bot", self._check("telegram", "Telegram on"))
        self._row(card, "Morning", self._check("morning_briefing", "Briefing on the first hello"))
        self._row(card, "Temperature", self._combo("temperature_unit", ("celsius", "fahrenheit")))
        self._row(card, "Whiteboard", self._check("whiteboard_on_top", "Keep it on top of other windows"))
        self._row(card, "See-through", self._slider("whiteboard_opacity", 40, 100),
                  note="% solid: lower shows more of what's behind the whiteboard")
        if IS_WINDOWS:
            import autostart
            self.values["start_at_login"] = autostart.is_on()
            self._row(card, "Start", self._check("start_at_login", "Start Jarvis with Windows"))

    # ----- actions -----
    def show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        if not self.values.get("reduce_motion"):
            self._fade_in()

    def _fade_in(self, steps=9, ms=18):
        """Fade the window in rather than popping it up (Windows and most Linux desktops)."""
        def frame(i):
            try:
                self.win.attributes("-alpha", min(1.0, (i / steps) ** 0.6))
                if i < steps:
                    self.win.after(ms, frame, i + 1)
            except tk.TclError:
                pass
        frame(1)

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _paint(self, button, colour):
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        button.configure(bg=colour, activebackground=colour, fg="#0b0f14" if r * .3 + g * .59 + b * .11 > 140 else FG)

    def pick_colour(self, key, button):
        _, chosen = colorchooser.askcolor(color=self.vars[key].get(), parent=self.win,
                                          title=f"{dict(COLOUR_LABELS)[key]} colour")
        if chosen:
            self.vars[key].set(chosen.lower())
            self._paint(button, chosen.lower())

    def default_colours(self, frame):
        for key, _ in COLOUR_LABELS:
            self.vars[key].set(settings.COLOURS[key])
        for b, (key, _) in zip([w for w in frame.winfo_children()][:len(COLOUR_LABELS)], COLOUR_LABELS):
            self._paint(b, settings.COLOURS[key])

    def preview(self, key):
        name = self.vars[key].get()
        self.status.set(f"Playing {name}...")

        def run():
            try:
                from audio import tts
                said = tts.preview_online(name) if key == "voice" else tts.preview(name)
            except Exception as e:
                said = f"Couldn't play it: {e}"
            print(f"[settings] {said}")
            try:
                self.win.after(0, lambda: self.status.set(said))
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=run, daemon=True, name="voice-preview").start()

    def collect(self) -> dict:
        out = {}
        for key, var in self.vars.items():
            value = var.get()
            as_type = getattr(var, "as_type", None)
            if as_type:
                value = as_type(round(float(value), 2))
            out[key] = value
        choice = out.pop("corner_choice", "keep where I put it")
        if choice in settings.CORNERS:
            out["corner"], out["position"] = choice, None
        if out.get("mic") == DEFAULT_MIC:
            out["mic"] = ""
        return out

    def save(self):
        values = self.collect()
        login = values.pop("start_at_login", None)
        moved = "position" in values and values["position"] is None and self.values.get("position") is not None
        moved = moved or values.get("corner", self.values.get("corner")) != self.values.get("corner")
        settings.save(values)
        if login is not None and IS_WINDOWS:
            import autostart
            print("[settings] " + autostart.set_on(bool(login)))
            if self.widget is not None and hasattr(self.widget, "autostart"):
                self.widget.autostart.set(bool(login))
        if values.get("telegram") and "telegram_bot" in sys.modules:
            sys.modules["telegram_bot"].start()   # turned back on: start it if it wasn't running
        if self.widget is not None:
            self.widget.apply_settings(moved_corner=moved)
        print("[settings] saved")
        self.close()

    def reset(self):
        settings.reset_all()
        if self.widget is not None:
            self.widget.apply_settings(moved_corner=True)
        self.status.set("Everything is back to the defaults.")
        self.close()
