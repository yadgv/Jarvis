"""JARVIS - Phase 1: wake word -> listen -> think -> speak."""
import queue
import re
import sys
import threading
import time
from datetime import datetime

import startup  # noqa: F401  (first, so its clock starts at launch)
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
from audio import ducking, smart_turn
from brain.llm import clip_last_reply, reset, think_stream
from skills import briefing, jobs, mcp_tools, reminders, system, timers
import skills  # noqa: E402
import telegram_bot  # noqa: E402
import dictation  # noqa: E402
import room_context  # noqa: E402

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
ANSWER_NOTE = "[He's answering the question you just asked him.]\n"
last_ignored = False  # the last follow-up wasn't meant for Jarvis
# His last spoken sentence was a question ("Shall I send it?"), so a bare
# "yes" or "no" straight after is an answer, not the end of the chat.
asked_question = False


def followup_options(followup: bool) -> dict:
    """How to think about something heard without the wake word. Straight
    after he asked a question it's the answer, so it's never ignored."""
    if followup and asked_question:
        return {"note": ANSWER_NOTE}
    return {"followup": True} if followup else {}


def is_acknowledgement(said: str) -> bool:
    words = [w for w in said.split() if w not in ("jarvis", "sir")]
    return not words or " ".join(words) in ACKNOWLEDGEMENTS


# Said during a conversation, these close it politely: he's done for now.
CLOSERS = {
    "thanks", "thank you", "thanks a lot", "thank you so much", "cheers", "that's all", "that's it",
    "that is all", "that'll be all", "that will be all", "i'm good", "im good", "i'm done", "all good",
    "never mind", "nevermind", "nothing", "no thanks", "no thank you", "that's everything",
    "bye", "goodbye", "good bye", "see you", "see ya", "later", "talk later", "stop listening",
    "it's okay", "it's ok", "it's fine", "that's fine", "we're good", "i'm all set", "all set", "nothing else",
    "that's all for now", "no that's it", "that's enough",
}
# The answer to "anything else?" that still ends it, even right after he asked a question.
FINAL_CLOSERS = {"that's everything", "that's all", "that's it", "that is all", "that'll be all", "nothing",
                 "nothing else", "no thanks", "no thank you", "i'm good", "im good", "i'm done", "all good",
                 "it's okay", "it's ok", "it's fine", "we're good", "i'm all set", "all set", "never mind",
                 "nevermind", "bye", "goodbye", "see you", "see ya", "that's all for now", "no that's it"}
CLOSE_WORDS = {"jarvis", "sir", "ok", "okay", "alright", "cool", "great", "perfect", "that's", "for", "now",
               "then", "so", "yeah", "no", "awesome", "nice", "good"}


def is_closer(said: str) -> bool:
    """ "Thanks", "that's all for now", "okay that's it Jarvis": the conversation is over."""
    if said in CLOSERS:
        return True
    text, found = f" {said} ", False
    for phrase in sorted(CLOSERS, key=len, reverse=True):   # take out every closing phrase
        if f" {phrase} " in text:
            text, found = text.replace(f" {phrase} ", " "), True
    return found and all(w in CLOSE_WORDS for w in text.split())


def sign_off(said: str) -> str:
    return "Anytime, sir." if "thank" in said or "cheers" in said else "Very good, sir."


def conversation_seconds() -> float:
    """How long he can stay quiet before the conversation ends (wake word needed
    again). Longer straight after Jarvis asked him something."""
    secs = float(config.FOLLOWUP_SECONDS)
    if secs <= 0:
        return 0.0
    return secs + (8 if asked_question else 0)


def followup_action(said: str, answering: bool, addressed: bool = False) -> str:
    """What to do with words heard mid-conversation (no wake word):
    'answer' (think and reply), 'name' (just "Jarvis": chime and listen),
    'close' (he's done: sign off) or 'quiet' ("ok", "cool": keep listening, say nothing)."""
    if is_just_name(said):
        return "name"
    if answering:
        # "Anything else?" "That's everything." is still the end.
        return "close" if is_closer(said) and any(f" {p} " in f" {said} " for p in FINAL_CLOSERS) else "answer"
    if is_closer(said) or (is_exit(said) and "jarvis" not in said and not addressed):
        return "close"
    if is_acknowledgement(said):
        return "quiet"
    return "answer"


# Clears the conversation. Saved facts stay; ask "forget that my..." to drop one.
RESET_PHRASES = {"new conversation", "start over", "start a new conversation"}


# His name as Whisper sometimes hears it ("Travis", "Jervis").
NAME_WORDS = r"(?:jarvis|jervis|jarvas|javis|jarvi|jarves|jarvus|travis|charvis|garvis)"
_LEAD = r"(?:(?:hey|hi|ok|okay|yo|oi|uh|um+|uhm|erm|so|oh|and|alright|right|well)\W+)*"
# "Travis is coming over" is about someone else: a misheard name only counts
# when it isn't followed by what you'd say about a person.
_ABOUT = r"(?!\s+(?:is|was|said|says|and|has|had|will|told|wants|'s)\b)(?!'s)"
_NAME_START = re.compile(r"^\W*" + _LEAD + r"(?:jarvis\b(?!'s)|" + NAME_WORDS + r"\b" + _ABOUT + r")[\s,.!?;:-]*", re.I)
_NAME_END = re.compile(r"[\s,]+" + NAME_WORDS + r"(?=\W*$)", re.I)
_NAME_ANY = re.compile(r"\bjarvis\b", re.I)


def strip_name(text: str):
    """(addressed, rest): his name taken off the front or end of what was said.
    People say the name of whoever they're talking to all the time ("Jarvis,
    and what about Friday?", "what do you think, Jarvis?"); it means "this is
    for you", never "start over". rest is "" when it was only the name."""
    text = (text or "").strip()
    rest = _NAME_START.sub("", text, count=1)
    addressed = rest != text
    shorter = _NAME_END.sub("", rest)
    if shorter != rest:
        addressed, rest = True, shorter
    addressed = addressed or bool(_NAME_ANY.search(rest))
    if not re.search(r"[a-z0-9]", rest, re.I):
        rest = ""
    elif rest[:1].islower() and rest[:1] != text[:1]:
        rest = rest[0].upper() + rest[1:]
    return addressed, rest.strip()


def is_just_name(said: str) -> bool:
    """ "Jarvis", "hey Jarvis" or "uh, Jarvis" on its own: he's calling for attention."""
    addressed, rest = strip_name(said)
    return addressed and (not rest or normalize(rest) in {"sir", "you there", "are you there"})


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


def pending_task_result():
    """A finished background job's report waiting in the inbox (taken out), or None.
    Said during the conversation it belongs to, not minutes later out of the blue."""
    found, others = None, []
    while True:
        try:
            item = ui_events.inbox.get_nowait()
        except queue.Empty:
            break
        if found is None and item and item[0] == "task_result":
            found = item[1]
        else:
            others.append(item)
    for item in others:
        ui_events.inbox.put(item)
    return found


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
        # Long tools get short spoken updates ("Working on it, sir.") in between.
        skills.set_progress_handler(lambda line: put((line, tts.synthesize(line), "progress")))
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
            skills.set_progress_handler(None)
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
    spoken = []  # what he actually got to say, for the history if he's cut off
    try:
        while not interrupted.is_set():
            try:
                item = clips.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            sentence, clip = item[0], item[1]
            is_progress = len(item) > 2  # "One moment, sir." etc.: not part of the reply
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
            if not is_progress:
                asked_question = sentence.rstrip().rstrip("\"')]").endswith("?")
            started = time.perf_counter()
            if clip is not None:
                tts.play(clip)
            else:
                tts.speak_system(sentence)
            if ui_events.stop_speaking.is_set():
                interrupted.set()
            if not is_progress:
                spoken.append(heard_part(sentence, time.perf_counter() - started)
                              if interrupted.is_set() else sentence)
    finally:
        if watcher is not None:
            stop_watch.set()
            watcher.join(timeout=1)
            stream.stop()
    if interrupted.is_set():
        print("[interrupted]")
        clip_last_reply(" ".join(p for p in spoken if p))
    return interrupted.is_set()


WORDS_PER_SECOND = 2.6  # roughly how fast he talks


def heard_part(sentence: str, seconds: float) -> str:
    """The words of a sentence he got through before being cut off, guessed
    from how long it played (GLaDOS's clip_interrupted_sentence, MIT, does
    the same with the share of audio played)."""
    words = sentence.split()
    share = max(0.0, min(1.0, seconds * WORDS_PER_SECOND / max(1, len(words))))
    return " ".join(words[: round(share * len(words))])


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
    ducking.restore()  # conversation over: music back up
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


def _start_extras():
    """The parts that don't need to be ready for the first "Hey Jarvis": started
    in the background once he's online, each timed in the log."""
    for name, start in (("phone bot (Telegram)", telegram_bot.start), ("dictation key", dictation.start),
                        ("MCP tools", mcp_tools.start), ("end-of-sentence model", smart_turn.load),
                        ("notes for when you're back", skills.sticky.start),
                        ("browser extension link", skills.browser_bridge.start),
                        ("phone alerts check", lambda: print(skills.phone.status()))):
        t = time.perf_counter()
        try:
            start()
        except Exception as e:
            print(f"[startup] {name} failed: {type(e).__name__}: {e}")
        startup.mark(f"{name} started", t)


def main():
    startup.mark("modules loaded")
    from brain import settings as saved_settings
    saved_settings.apply()  # choices from the orb's Settings window (mic, wake sensitivity, ...)
    timers.announce = say
    reminders.start()  # also reads out any that came due while he was off
    jobs.start()  # standing jobs and watches from memory/jobs.json
    threading.Thread(target=_start_extras, daemon=True, name="startup-extras").start()
    print("JARVIS online.")
    startup.mark("online")
    say("Jarvis online. At your service, sir.")

    with open_stream() as stream:
        if config.AUTO_CALIBRATE:
            calibrate(stream)
        startup.mark("ready to listen")

        need_wake = True
        room = None
        conv_until = 0.0  # in a conversation until then: no wake word needed
        already_woken = False  # you said "Hey Jarvis" (or pressed Stop) to interrupt him
        named_last = False     # he just said "Jarvis" and paused: the rest is coming
        while True:
            typed = None
            if need_wake:
                if already_woken:
                    already_woken = False
                    kind = "talk"
                else:
                    kind, typed = wait_for_trigger(stream)
                if kind == "task_result":
                    # A background job finished: tell him now, while it's quiet.
                    stream.stop()
                    ducking.duck()
                    was_interrupted = respond(typed, None, stream)
                    stream.start()
                    need_wake = was_interrupted or config.FOLLOWUP_SECONDS <= 0
                    already_woken = was_interrupted
                    conv_until = time.time() + conversation_seconds()
                    continue
                room = room_context.start() if kind == "wake" else None
                if kind != "text":
                    ducking.duck()  # music down while he listens and talks
                    beep = chime(stream)
                    print("[listening]")
                    ui_events.emit("status", "listening")
                    audio = record_until_silence(stream, ignore_seconds=beep or 0)
            else:
                note = pending_task_result()
                if note:
                    # A job he started finished while we were talking: tell him now.
                    stream.stop()
                    was_interrupted = respond(note, None, stream)
                    stream.start()
                    conv_until = time.time() + conversation_seconds()
                    if was_interrupted:
                        need_wake, already_woken = True, True
                    continue
                left = conv_until - time.time()
                if left <= 0.5:
                    print("[conversation over: quiet for a while; say the wake word to start again]")
                    need_wake = True
                    ducking.restore()
                    ui_events.emit("status", "idle")
                    continue
                print(f"[listening for a follow-up... {left:.0f}s left in the conversation]")
                ui_events.emit("status", "listening")
                audio = record_until_silence(stream, left)
                if not len(audio):
                    print("[conversation over: no reply]")
                    need_wake = True
                    ducking.restore()
                    ui_events.emit("status", "idle")
                    stream.start()
                    continue

            # Pause the mic while we transcribe, think and speak, so stale
            # audio (and Jarvis's own voice) doesn't pile up in the buffer.
            stream.stop()
            t_heard = time.perf_counter()

            if typed is not None:
                text = typed.strip()
            else:
                text = transcribe(audio) if len(audio) else ""
            if not text:
                if typed is None and len(audio):
                    print("[heard sound but couldn't make out words]")
                    if need_wake:
                        # He woke Jarvis and said something: don't just drop it.
                        say("Sorry, sir, I didn't catch that.")
                        conv_until = time.time() + conversation_seconds()
                    need_wake = conv_until <= time.time() or config.FOLLOWUP_SECONDS <= 0
                else:
                    need_wake = True
                stream.start()
                continue
            print(f"You: {text}  [{'typed' if typed is not None else f'stt {time.perf_counter() - t_heard:.1f}s'}]")
            ui_events.emit("you", text)

            in_conversation = (not need_wake or named_last) and typed is None
            # His name at the start or end ("Jarvis, and Friday?") just means
            # "this is for you": same conversation, same context, never a restart.
            addressed, rest = strip_name(text) if typed is None else (False, text)
            if addressed and not rest:
                # Only his name (or he paused right after it): keep listening for
                # the rest, quietly. No chime, nothing reset.
                print("[heard my name: still listening, same conversation]")
                named_last = True
                conv_until = max(conv_until, time.time() + conversation_seconds())
                need_wake = False
                stream.start()
                continue
            addressed = addressed or named_last
            named_last = False
            if addressed:
                text = rest
            said = normalize(text)
            # Right after he asked a question, whatever is said next is the answer:
            # never dropped as chatter or as the end of the conversation.
            answering = in_conversation and asked_question
            action = followup_action(said, answering, addressed) if in_conversation else "answer"
            # Said to him by name, it's never overheard chatter.
            followup = in_conversation and not addressed
            if action == "name":
                action = "quiet"
            if action == "close":
                # "Thanks", "that's all", "bye": the conversation is over.
                print("[conversation over: he said he's done]")
                say(sign_off(said))
                need_wake, conv_until = True, 0.0
                ducking.restore()
                stream.start()
                continue
            if action == "quiet":
                # "Ok", "cool": nothing to answer, but he may still go on.
                print("[follow-up: just an acknowledgement, still listening]")
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

            extra = followup_options(followup) if not answering else {"note": ANSWER_NOTE}
            if not followup and briefing.is_first_hello(said):
                extra["note"] = briefing.NOTE  # first hello of the day: give the morning briefing
                briefing.mark_briefed()
            if need_wake and room is not None:
                heard = room_context.result(room)
                if heard:
                    extra["note"] = extra.get("note", "") + room_context.note(heard)
            was_interrupted = respond(text, t_heard, stream, **extra)
            if system.shutdown_requested:
                break

            stream.start()
            if was_interrupted:
                need_wake, already_woken = True, True  # go straight to listening
            elif typed is not None:
                need_wake = True  # typed chat: wait for the next message or wake word
            elif last_ignored:
                # Chatter that wasn't for him: keep the conversation open for
                # what's left of it, without starting the clock again.
                need_wake = conv_until <= time.time()
            else:
                # In a conversation: keep listening (no wake word) until he's
                # quiet for a while or says he's done.
                conv_until = time.time() + conversation_seconds()
                need_wake = config.FOLLOWUP_SECONDS <= 0
    ducking.restore()
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
