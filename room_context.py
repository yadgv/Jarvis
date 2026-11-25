"""'Third person in the room' (off by default: ROOM_CONTEXT in config.py).

While waiting for "Hey Jarvis", the last ROOM_CONTEXT_SECONDS of sound are
kept in memory (audio/wakeword.py). When you call him, that audio is turned
into text on this PC while you're talking, and handed to Claude as background
for this one question, so "Jarvis, what do you think?" or "settle this for us"
works. It's never saved, and never added to the conversation history.
Idea from isair/jarvis ("A third person in the room")."""
import threading

import config

MIN_WORDS = 4
NOTE = ("[Background, not a request: this is what was being said in the room just before he called you "
        "(automatic transcript, may contain other people and mistakes). Use it only if his question refers "
        "to it, e.g. 'what do you think?', and don't quote it back at length:\n{text}]\n")


def start():
    """Begin transcribing the room audio in the background; None if off or empty."""
    if not config.ROOM_CONTEXT:
        return None
    from audio import wakeword
    audio = wakeword.take_room_audio()
    if len(audio) < config.SAMPLE_RATE:
        return None
    holder = {"done": threading.Event(), "text": ""}

    def work():
        try:
            from audio.stt import transcribe
            holder["text"] = transcribe(audio)
        except Exception as e:
            print(f"[room] couldn't transcribe: {e}")
        finally:
            holder["done"].set()
    threading.Thread(target=work, daemon=True).start()
    return holder


def result(holder, timeout=8.0) -> str:
    if holder is None or not holder["done"].wait(timeout):
        return ""
    text = holder["text"].strip()
    if len(text.split()) < MIN_WORDS:
        return ""
    print(f"[room] heard before the wake word: {text[:200]}")
    return text


def note(text: str) -> str:
    return NOTE.format(text=text)
