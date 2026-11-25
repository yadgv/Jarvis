"""JARVIS desktop window.

    python gui.py

Shows the conversation and what Jarvis is doing, lets you type instead of
talking, and has a Talk button (no wake word needed) that turns into Stop
while he's speaking. "Hey Jarvis" keeps working as usual.
Uses tkinter, which comes with Python on Windows and is one apt package on a Pi
(sudo apt install python3-tk).
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont

import config
import ui_events

BG, PANEL, TEXT, MUTED = "#0f1419", "#1a2129", "#e6edf3", "#8b98a5"
ACCENT, YOU, JARVIS = "#3fb6ff", "#9ece6a", "#7dcfff"
STATUS = {  # status -> (label, colour)
    "starting": ("Starting up…", MUTED),
    "idle": ("Say “Hey Jarvis”, press Talk, or type", MUTED),
    "listening": ("Listening…", "#9ece6a"),
    "thinking": ("Thinking…", "#e0af68"),
    "speaking": ("Speaking…", ACCENT),
    "off": ("Jarvis is off", "#f7768e"),
}


class JarvisWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.status = "starting"
        self.last_speaker = None

        root.title("JARVIS")
        root.geometry("560x680")
        root.minsize(420, 420)
        root.configure(bg=BG)
        base = tkfont.nametofont("TkDefaultFont").actual("family")
        self.f_body = (base, 12)
        self.f_name = (base, 10, "bold")
        self.f_title = (base, 18, "bold")

        # Header: title + status light
        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text="J.A.R.V.I.S.", font=self.f_title, fg=ACCENT, bg=BG).pack(side="left")
        self.dot = tk.Canvas(top, width=14, height=14, bg=BG, highlightthickness=0)
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill=MUTED, outline="")
        self.status_label = tk.Label(top, text="", font=(base, 10), fg=MUTED, bg=BG)
        self.status_label.pack(side="right")
        self.dot.pack(side="right", padx=(0, 6))

        # Input row (packed before the conversation so it always keeps its space)
        row = tk.Frame(root, bg=BG)
        row.pack(side="bottom", fill="x", padx=16, pady=(6, 16))

        # Conversation
        box = tk.Frame(root, bg=PANEL)
        box.pack(fill="both", expand=True, padx=16, pady=6)
        self.chat = tk.Text(box, wrap="word", bg=PANEL, fg=TEXT, font=self.f_body, relief="flat",
                            padx=12, pady=10, state="disabled", cursor="arrow", spacing3=4,
                            highlightthickness=0, borderwidth=0)
        scroll = tk.Scrollbar(box, command=self.chat.yview)
        self.chat.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("you_name", foreground=YOU, font=self.f_name, spacing1=10)
        self.chat.tag_configure("jarvis_name", foreground=JARVIS, font=self.f_name, spacing1=10)
        self.chat.tag_configure("info", foreground=MUTED, font=(base, 10, "italic"), spacing1=6)

        self.entry = tk.Entry(row, font=self.f_body, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              relief="flat", highlightthickness=1, highlightbackground=PANEL,
                              highlightcolor=ACCENT)
        self.entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry.bind("<Return>", lambda e: self.send())
        self._button(row, "Send", self.send).pack(side="left", padx=(8, 0))
        self.talk_btn = self._button(row, "🎤 Talk", self.talk)
        self.talk_btn.pack(side="left", padx=(8, 0))
        root.bind("<Escape>", lambda e: self.talk() if self.status == "speaking" else None)

        self.set_status("starting")
        self.entry.focus_set()
        ui_events.on(lambda kind, text: self.events.put((kind, text)))
        root.after(100, self.pump)

    def _button(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, font=self.f_name, bg=ACCENT, fg=BG,
                         activebackground=TEXT, relief="flat", padx=14, pady=6, cursor="hand2")

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
            from audio import tts
            tts.stop()
        elif self.status == "idle":
            ui_events.inbox.put(("talk", None))

    # ----- updates from the voice loop -----
    def pump(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "status":
                    self.set_status(text)
                elif kind in ("you", "jarvis", "info"):
                    self.add(kind, text)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def set_status(self, status):
        self.status = status
        label, colour = STATUS.get(status, (status, MUTED))
        self.status_label.configure(text=label, fg=colour)
        self.dot.itemconfigure(self.dot_id, fill=colour)
        self.talk_btn.configure(text="■ Stop" if status == "speaking" else "🎤 Talk",
                                state="normal" if status in ("idle", "speaking") else "disabled")
        if status in ("idle", "listening"):
            self.last_speaker = None  # next Jarvis line starts a new bubble

    def add(self, who, text):
        self.chat.configure(state="normal")
        if who == "info":
            self.chat.insert("end", text + "\n", "info")
        elif who == self.last_speaker == "jarvis":
            # Jarvis speaks sentence by sentence: keep one reply together.
            self.chat.delete("end-2c")
            self.chat.insert("end", " " + text + "\n")
        else:
            self.chat.insert("end", ("You" if who == "you" else "Jarvis") + "\n", f"{who}_name")
            self.chat.insert("end", text + "\n")
        self.last_speaker = who
        self.chat.configure(state="disabled")
        self.chat.see("end")


def run_voice_loop():
    import main  # loads the speech models; the window is already showing
    if config.LOG_FILE:
        sys.stdout = main._Tee(sys.stdout, config.LOG_FILE)
    try:
        main.main()
    except Exception as e:
        ui_events.emit("info", f"Voice loop stopped: {e}")
        print(f"[voice loop error] {e}")
    ui_events.emit("status", "off")


def start():
    ui_events.gui_active = True
    root = tk.Tk()
    JarvisWindow(root)
    threading.Thread(target=run_voice_loop, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))  # closing the window stops Jarvis
    root.mainloop()


if __name__ == "__main__":
    start()
