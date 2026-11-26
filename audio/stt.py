"""Speech-to-text with faster-whisper (runs locally)."""
from faster_whisper import WhisperModel

import config


def _load():
    """Use the copy already on disk first, so starting with no internet doesn't
    wait on a download check; download it only if it isn't there yet."""
    opts = dict(device=config.WHISPER_DEVICE, compute_type=config.WHISPER_COMPUTE)
    try:
        return WhisperModel(config.WHISPER_MODEL, local_files_only=True, **opts)
    except Exception:
        return WhisperModel(config.WHISPER_MODEL, **opts)


_model = _load()


import numpy as np

# Warm up once at startup so the first real question isn't slow.
try:
    list(_model.transcribe(np.random.uniform(-0.01, 0.01, 16000).astype(np.float32),
                           language="en", beam_size=1)[0])
except Exception:
    pass


def transcribe(audio) -> str:
    if len(audio) == 0:
        return ""
    segments, _ = _model.transcribe(
        audio, language="en", beam_size=1, vad_filter=True,
        without_timestamps=True, condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()
