"""JARVIS - Phase 1: wake word -> listen -> think -> speak."""
import queue
import re
import sys
import threading
import time
from datetime import datetime

import config
import ui_events


class _Tee:
    """Copies everything printed to the console into jarvis.log, with times."""

    def __init__(self, stream, path):
        self.stream, self.file, self.line_start = stream, open(path, "a", encoding="utf-8"), True

    def write(self, text):
        if self.stream is not None:  # None when started without a console (pythonw)
            self.stream.write(text)
        for part in text.splitlines(keepends=True):
            if self.line_start and part.strip():
                self.file.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S  "))
            self.file.write(part)
            self.line_start = part.endswith("\n")
        self.file.flush()

    def flush(self):
        if self.stream is not None:
            self.stream.flush()


if config.LOG_FILE and __name__ == "__main__":
    sys.stdout = _Tee(sys.stdout, config.LOG_FILE)
from audio import tts
from audio.recorder import calibrate, chime, open_stream, record_until_silence
from audio.stt import transcribe
from audio.tts import speak
from brain.llm import reset, think_stream
from skills import briefing, reminders, system, timers

watch_for_interrupt = None
if config.MODE == "wake":
    from audio.wakeword import wait_for_wake_word, watch_for_interrupt

# After trimming filler words ("okay", "please", "Jarvis"...) from both ends,
# the whole sentence has to be one of these, so "don't shut down the PC"
# doesn't turn Jarvis off. Anything else ("that's all for today, go to sleep")
# is left to Claude, which can call the shut_down tool.
EXIT_PHRASES = {
    "goodbye", "bye", "good bye", "shut down", "shutdown", "power down",
    "power off", "turn off", "go to sleep",
}
FILLER = {"okay", "ok", "please", "now", "alright", "hey", "jarvis", "you", "can",
          "then", "so", "well", "thanks", "thank", "right", "just", "yes", "yeah", "and"}
# Said after a reply without the wake word, these just end the conversation
# quietly ("I understand" to someone else used to get a reply, or worse).
ACKNOWLEDGEMENTS = {
    "i understand", "understood", "i see", "ok", "okay", "cool", "nice", "great", "got it",
    "thanks", "thank you", "alright", "yeah", "yes", "no", "mm", "hmm", "uh huh", "right",
    "sure", "fine", "perfect", "good", "awesome", "oh", "ah", "wow", "lol", "same", "true",
}
# Short replies that answer his question rather than end the conversation.
ANSWERS = {"yes", "no", "yeah", "yep", "nope", "sure", "ok", "okay", "do it", "go ahead", "send it",
           "yes please", "no thanks", "yes send it", "please do", "alright", "fine", "right"}
last_ignored = False  # the last follow-up wasn't meant for Jarvis
# His last spoken sentence was a question ("Shall I send it?"), so a bare
# "yes" or "no" straight after is an answer, not the end of the chat.
asked_question = False


def is_acknowledgement(said: str) -> bool:
    words = [w for w in said.split() if w not in ("jarvis", "sir")]
    return not words or " ".join(words) in ACKNOWLEDGEMENTS


# Clears the conversation. Saved facts stay; ask "forget that my..." to drop one.
RESET_PHRASES = {"new conversation", "start over", "start a new conversation"}


def normalize(text: str) -> str:
    text = re.sub(r"[^a-z' ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def is_exit(said: str) -> bool:
    words = said.split()
    while words and words[0] in FILLER:
        words.pop(0)
    while words and words[-1] in FILLER:
        words.pop()
    return " ".join(words) in EXIT_PHRASES


def respond(text: str, t_heard: float = None, stream=None, followup: bool = False, note: str = "") -> bool:
    """Think and speak at the same time: while one sentence plays, the next
    is already being written by Claude and turned into audio.
    If barge-in is on, "Hey Jarvis" while he's talking cuts him off.
    followup=True: heard without the wake word, so stay quiet if it wasn't
    meant for him (sets last_ignored).
    Returns True if he was interrupted."""
    global last_ignored, asked_question
    last_ignored = False
    asked_question = False
    clips = queue.Queue(maxsize=3)
    interrupted = threading.Event()
    ui_events.stop_speaking.clear()
    ui_events.emit("status", "thinking")

    def put(item):
        while not interrupted.is_set():
            try:
                clips.put(item, timeout=0.2)
                return
            except queue.Full:
                pass

    def produce():
        count = 0
        try:
            extra = {k: v for k, v in (("followup", followup), ("note", note)) if v}
            for sentence in think_stream(text, **extra):
                if interrupted.is_set():
                    break
                count += 1
                # Start the voice now; the text is shown when it starts playing.
                put((sentence, tts.synthesize(sentence)))
            if count == 0 and followup and not interrupted.is_set():
                global last_ignored
                last_ignored = True   # not for him: say nothing
            elif count == 0 and not interrupted.is_set():
                # Never leave him hanging in silence.
                msg = "Sorry, sir, I lost my train of thought. Could you say that again?"
                put((msg, tts.synthesize(msg)))
        except Exception as e:
            print(f"[brain error] {e}")
            if count == 0:
                msg = "I'm having trouble reaching my servers, sir."
                put((msg, tts.synthesize(msg)))
        finally:
            put(None)

    # Listen for "Hey Jarvis" while he talks.
    stop_watch = threading.Event()
    watcher = None
    if stream is not None and watch_for_interrupt and config.MODE == "wake" and config.BARGE_IN:
        def on_wake():
            interrupted.set()
            tts.stop()
        stream.start()
        watcher = threading.Thread(target=watch_for_interrupt, args=(stream, stop_watch, on_wake), daemon=True)
        watcher.start()

    threading.Thread(target=produce, daemon=True).start()
    first = True
    try:
        while not interrupted.is_set():
            try:
                item = clips.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            sentence, clip = item
            if first:
                ui_events.emit("status", "speaking")
            if first and t_heard is not None:
                print(f"[time] reply started {time.perf_counter() - t_heard:.1f}s after you stopped talking")
            first = False
            if ui_events.stop_speaking.is_set():
                interrupted.set()
            if interrupted.is_set():
                break
            # Show each sentence as he starts saying it, so text and voice line up.
            print(f"JARVIS: {sentence}")
            ui_events.emit("jarvis", sentence)
            asked_question = sentence.rstrip().rstrip("\"')]").endswith("?")
            if clip is not None:
                tts.play(clip)
            else:
                tts.speak_system(sentence)
            if ui_events.stop_speaking.is_set():
                interrupted.set()
    finally:
        if watcher is not None:
            stop_watch.set()
            watcher.join(timeout=1)
            stream.stop()
    if interrupted.is_set():
        print("[interrupted]")
    return interrupted.is_set()


def say(text: str):
    """Speak a fixed line (and show it in the window)."""
    print(f"JARVIS: {text}")
    ui_events.emit("jarvis", text)
    ui_events.emit("status", "speaking")
    speak(text)


def wait_for_trigger(stream):
    """Block until you say "Hey Jarvis", press Talk, or type a message.
    Returns ("wake", None), ("talk", None) or ("text", message)."""
    ui_events.emit("status", "idle")
    if config.MODE == "wake":
        print("\n[waiting for 'Hey Jarvis'...]")
        return wait_for_wake_word(stream, poll=ui_events.poll) or ("wake", None)
    stream.stop()
    try:
        if ui_events.gui_active:
            return ui_events.inbox.get()
        input("\n[press Enter to talk]")
        return ("talk", None)
    finally:
        stream.start()


def main():
    timers.announce = say
    reminders.start()  # also reads out any that came due while he was off
    print("JARVIS online.")
    say("Jarvis online. At your service, sir.")

    with open_stream() as stream:
        if config.AUTO_CALIBRATE:
            calibrate(stream)

        need_wake = True
        already_woken = False  # you said "Hey Jarvis" (or pressed Stop) to interrupt him
        while True:
            typed = None
            if need_wake:
                if already_woken:
                    already_woken = False
                    kind = "talk"
                else:
                    kind, typed = wait_for_trigger(stream)
                if kind != "text":
                    chime(stream)
                    print("[listening]")
                    ui_events.emit("status", "listening")
                    audio = record_until_silence(stream)
            else:
                print("[listening for a follow-up...]")
                ui_events.emit("status", "listening")
                audio = record_until_silence(stream, config.FOLLOWUP_SECONDS)

            # Pause the mic while we transcribe, think and speak, so stale
            # audio (and Jarvis's own voice) doesn't pile up in the buffer.
            stream.stop()
            t_heard = time.perf_counter()

            if typed is not None:
                text = typed.strip()
            else:
                text = transcribe(audio) if len(audio) else ""
            if not text:
                if need_wake and typed is None and len(audio):
                    print("[heard sound but couldn't make out words]")
                need_wake = True
                stream.start()
                continue
            print(f"You: {text}  [{'typed' if typed is not None else f'stt {time.perf_counter() - t_heard:.1f}s'}]")
            ui_events.emit("you", text)

            said = normalize(text)
            followup = not need_wake and typed is None
            answering = followup and asked_question and said in ANSWERS
            if followup and not answering and (is_acknowledgement(said) or (is_exit(said) and "jarvis" not in said)):
                # "I understand", "bye" etc. without his name: end the chat quietly.
                print("[follow-up ignored: sounded like the end of the conversation]")
                need_wake = True
                stream.start()
                continue
            if is_exit(said):
                say("Powering down. Goodbye, sir.")
                break
            if said in RESET_PHRASES:
                reset()
                say("Very well, sir. Fresh start.")
                need_wake = True
                stream.start()
                continue

            extra = {"followup": True} if followup else {}
            if not followup and briefing.is_first_hello(said):
                extra["note"] = briefing.NOTE  # first hello of the day: give the morning briefing
                briefing.mark_briefed()
            was_interrupted = respond(text, t_heard, stream, **extra)
            if system.shutdown_requested:
                break

            stream.start()
            if was_interrupted:
                need_wake, already_woken = True, True  # go straight to listening
            elif typed is not None or last_ignored:
                need_wake = True  # typed chat: wait for the next message or wake word
            else:
                # Keep listening briefly so you can reply without the wake word.
                need_wake = config.FOLLOWUP_SECONDS <= 0
    ui_events.emit("status", "off")


if __name__ == "__main__":
    if "--gui" in sys.argv:  # same as running gui.py
        import gui
        gui.launch()
        sys.exit()
    try:
        main()
    except KeyboardInterrupt:
        print("\nJARVIS offline.")
