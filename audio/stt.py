"""Speech-to-text with faster-whisper (runs locally)."""
import re
import threading
import time

import numpy as np
from faster_whisper import WhisperModel

import config
import startup


def _load_one(name):
    """Use the copy already on disk first, so starting with no internet doesn't
    wait on a download check; download it only if it isn't there yet."""
    opts = dict(device=config.WHISPER_DEVICE, compute_type=config.WHISPER_COMPUTE)
    try:
        return WhisperModel(name, local_files_only=True, **opts)
    except Exception:
        return WhisperModel(name, **opts)


def _load():
    """The chosen model, else the smaller fallback (say the bigger one can't be
    downloaded right now): hearing a bit worse beats not hearing at all."""
    try:
        return _load_one(config.WHISPER_MODEL)
    except Exception as e:
        backup = getattr(config, "WHISPER_FALLBACK_MODEL", "")
        if not backup or backup == config.WHISPER_MODEL:
            raise
        print(f"[stt] couldn't load {config.WHISPER_MODEL} ({type(e).__name__}); using {backup}")
        return _load_one(backup)


VOCAB_FILE = "vocab.json"


def words() -> list:
    """His words Whisper should expect: config.STT_WORDS, ones he taught
    ("learn the word ..."), and his Canvas class names."""
    found = list(getattr(config, "STT_WORDS", []) or [])
    try:
        from brain import memory
        learned = memory._read(VOCAB_FILE, [])
        found += [w for w in learned if isinstance(w, str)] if isinstance(learned, list) else []
        canvas = memory._read("canvas.json", {})
        if isinstance(canvas, dict):
            found += [n for n in canvas.get("course_names", []) if isinstance(n, str)]
    except Exception:
        pass
    seen, out = set(), []
    for w in found:
        w = " ".join(w.split())[:60]
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def hint() -> str:
    """Whisper's initial prompt: it reads like earlier text, so the words in it
    come out spelled right instead of as sound-alikes ("bare book" -> breadboard).
    Kept short: Whisper only looks at the last ~220 tokens of it anyway."""
    vocab = words()
    if not vocab:
        return ""
    text = ""
    for w in vocab:
        if len(text) + len(w) > 600:
            break
        text += (", " if text else "") + w
    return f"Talking to Jarvis about {text}."


_model = None
_ready = threading.Event()


def _load_and_warm():
    """In the background, so Jarvis is up while the model loads. Warming up
    once means the first real question isn't slow."""
    global _model
    t = time.perf_counter()
    try:
        _model = _load()
        list(_model.transcribe(np.random.uniform(-0.01, 0.01, 16000).astype(np.float32),
                               language="en", beam_size=1)[0])
    except Exception as e:
        print(f"[stt] {type(e).__name__}: {e}")
    finally:
        _ready.set()
        startup.mark("speech recognition (Whisper) loaded", t)


threading.Thread(target=_load_and_warm, daemon=True, name="whisper-load").start()


def _model_retry():
    global _model
    _model = _load()


def transcribe(audio, hints: bool = True) -> str:
    """hints=False for the "was that his name?" check, where hinting "Jarvis"
    would make other short words sound like it."""
    if len(audio) == 0:
        return ""
    if not _ready.is_set():
        print("[stt] still loading the speech model, one moment")
        _ready.wait(120)
    if _model is None:
        _model_retry()
    opts = dict(language="en", beam_size=max(1, int(getattr(config, "WHISPER_BEAM_SIZE", 1))),
                vad_filter=True, without_timestamps=True, condition_on_previous_text=False,
                # keep a little sound either side of each stretch of speech, so a
                # quiet last word isn't trimmed off ("...the whiteboard" -> "...the")
                vad_parameters={"speech_pad_ms": 400})
    prompt = hint() if hints else ""
    if prompt:
        opts["initial_prompt"] = prompt
    try:
        segments, _ = _model.transcribe(audio, **opts)
        text = " ".join(s.text.strip() for s in segments).strip()
    except TypeError:   # an older faster-whisper without some option: the plain way
        segments, _ = _model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
    return "" if prompt and _echoes_hint(text, prompt) else text


def _echoes_hint(text: str, prompt: str) -> bool:
    """Whisper sometimes "hears" the hint itself in noise: that's not him."""
    return "talking to jarvis about" in text.lower()
