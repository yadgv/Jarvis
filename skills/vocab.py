"""Teach Jarvis's hearing a word: "Jarvis, learn the word breadboard".

Speech recognition (Whisper) guesses from sound, so a word it doesn't expect
comes out as a sound-alike ("bare book" for breadboard). Words saved here are
given to it as a hint every time it listens (see audio/stt.py)."""
from brain import memory

FILE = "vocab.json"   # the same file audio/stt.py reads
MAX_WORDS = 60


def _load():
    words = memory._read(FILE, [])
    return [w for w in words if isinstance(w, str)] if isinstance(words, list) else []


def learn_word(a):
    word = " ".join(str((a or {}).get("word") or "").split())[:60].strip(" .,!?\"'")
    if not word:
        return "Ask him which word to learn, spelled out if it's unusual."
    words = [w for w in _load() if w.lower() != word.lower()]
    words.append(word)
    memory._write(FILE, words[-MAX_WORDS:])
    return f"Learned: I'll listen out for \"{word}\" from now on."


def forget_word(a):
    word = str((a or {}).get("word") or "").strip().lower()
    words = _load()
    kept = [w for w in words if w.lower() != word]
    if len(kept) == len(words):
        return f"\"{word}\" wasn't on my list of learned words."
    memory._write(FILE, kept)
    return f"Forgotten: {word}."


SKILLS = [
    {
        "name": "learn_word",
        "description": "Teach speech recognition a word he uses that keeps being misheard (a name, a class, "
                       "a technical term), e.g. 'learn the word breadboard', 'you keep mishearing Arduino'. "
                       "Give the correct spelling.",
        "parameters": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]},
        "run": learn_word,
    },
    {
        "name": "forget_word",
        "description": "Remove a word taught with learn_word.",
        "parameters": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]},
        "run": forget_word,
    },
]
