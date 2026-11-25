"""Speech-to-text with faster-whisper (runs locally)."""
from faster_whisper import WhisperModel

import config

_model = WhisperModel(
    config.WHISPER_MODEL,
    device=config.WHISPER_DEVICE,
    compute_type=config.WHISPER_COMPUTE,
)


def transcribe(audio) -> str:
    if len(audio) == 0:
        return ""
    segments, _ = _model.transcribe(
        audio, language="en", beam_size=1, vad_filter=True
    )
    return " ".join(s.text.strip() for s in segments).strip()
