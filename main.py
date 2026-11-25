"""JARVIS - Phase 1: wake word -> listen -> think -> speak."""
import queue
import re
import sys
import threading
import time
from datetime import datetime

import config


class _Tee:
    """Copies everything printed to the console into jarvis.log, with times."""

    def __init__(self, stream, path):
        self.stream, self.file, self.line_start = stream, open(path, "a", encoding="utf-8"), True

    def write(self, text):
        self.stream.write(text)
        for part in text.splitlines(keepends=True):
            if self.line_start and part.strip():
                self.file.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S  "))
            self.file.write(part)
            self.line_start = part.endswith("\n")
        self.file.flush()

    def flush(self):
        self.stream.flush()


if config.LOG_FILE and __name__ == "__main__":
    sys.stdout = _Tee(sys.stdout, config.LOG_FILE)
from audio import tts
from audio.recorder import calibrate, chime, open_stream, record_until_silence
from audio.stt import transcribe
from audio.tts import speak
from brain.llm import reset, think_stream
from skills import system, timers

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


def respond(text: str, t_heard: float = None, stream=None) -> bool:
    """Think and speak at the same time: while one sentence plays, the next
    is already being written by Claude and turned into audio.
    If barge-in is on, "Hey Jarvis" while he's talking cuts him off.
    Returns True if he was interrupted."""
    clips = queue.Queue(maxsize=3)
    interrupted = threading.Event()

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
            for sentence in think_stream(text):
                if interrupted.is_set():
                    break
                count += 1
                print(f"JARVIS: {sentence}")
                put((sentence, tts.synthesize(sentence)))
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
            if first and t_heard is not None:
                print(f"[time] reply started {time.perf_counter() - t_heard:.1f}s after you stopped talking")
            first = False
            if interrupted.is_set():
                break
            if clip is not None:
                tts.play(clip)
            else:
                tts.speak_system(sentence)
    finally:
        if watcher is not None:
            stop_watch.set()
            watcher.join(timeout=1)
            stream.stop()
    if interrupted.is_set():
        print("[interrupted]")
    return interrupted.is_set()


def main():
    timers.announce = lambda msg: (print(f"JARVIS: {msg}"), tts.speak(msg))
    print("JARVIS online.")
    speak("Jarvis online. At your service, sir.")

    with open_stream() as stream:
        if config.AUTO_CALIBRATE:
            calibrate(stream)

        need_wake = True
        already_woken = False  # you said "Hey Jarvis" to interrupt him
        while True:
            if need_wake:
                if already_woken:
                    already_woken = False
                elif config.MODE == "wake":
                    print("\n[waiting for 'Hey Jarvis'...]")
                    wait_for_wake_word(stream)
                else:
                    stream.stop()
                    input("\n[press Enter to talk]")
                    stream.start()
                chime(stream)
                print("[listening]")
                audio = record_until_silence(stream)
            else:
                print("[listening for a follow-up...]")
                audio = record_until_silence(stream, config.FOLLOWUP_SECONDS)

            # Pause the mic while we transcribe, think and speak, so stale
            # audio (and Jarvis's own voice) doesn't pile up in the buffer.
            stream.stop()
            t_heard = time.perf_counter()

            text = transcribe(audio) if len(audio) else ""
            if not text:
                if need_wake and len(audio):
                    print("[heard sound but couldn't make out words]")
                need_wake = True
                stream.start()
                continue
            print(f"You: {text}  [stt {time.perf_counter() - t_heard:.1f}s]")

            said = normalize(text)
            if is_exit(said):
                speak("Powering down. Goodbye, sir.")
                break
            if said in RESET_PHRASES:
                reset()
                speak("Very well, sir. Fresh start.")
                need_wake = True
                stream.start()
                continue

            was_interrupted = respond(text, t_heard, stream)
            if system.shutdown_requested:
                break

            stream.start()
            if was_interrupted:
                need_wake, already_woken = True, True  # go straight to listening
            else:
                # Keep listening briefly so you can reply without the wake word.
                need_wake = config.FOLLOWUP_SECONDS <= 0


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nJARVIS offline.")
