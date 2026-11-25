"""Speech-to-text with faster-whisper (runs locally)."""
from faster_whisper import WhisperModel

import config

_model = WhisperModel(
    config.WHISPER_MODEL,
    device=config.WHISPER_DEVICE,
    compute_type=config.WHISPER_COMPUTE,
)


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
