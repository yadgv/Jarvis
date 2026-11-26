"""Speech-to-text with faster-whisper (runs locally)."""
import threading
import time

import numpy as np
from faster_whisper import WhisperModel

import config
import startup


def _load():
    """Use the copy already on disk first, so starting with no internet doesn't
    wait on a download check; download it only if it isn't there yet."""
    opts = dict(device=config.WHISPER_DEVICE, compute_type=config.WHISPER_COMPUTE)
    try:
        return WhisperModel(config.WHISPER_MODEL, local_files_only=True, **opts)
    except Exception:
        return WhisperModel(config.WHISPER_MODEL, **opts)


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


def transcribe(audio) -> str:
    if len(audio) == 0:
        return ""
    if not _ready.is_set():
        print("[stt] still loading the speech model, one moment")
        _ready.wait(120)
    if _model is None:
        _model_retry()
    segments, _ = _model.transcribe(
        audio, language="en", beam_size=1, vad_filter=True,
        without_timestamps=True, condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()
