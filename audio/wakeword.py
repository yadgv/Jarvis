"""Listens for "Hey Jarvis" using openWakeWord (free, runs on the Pi)."""
import openwakeword
from openwakeword.model import Model

import config
from audio.recorder import CHUNK

openwakeword.utils.download_models()  # one-time download, cached after
_model = Model(wakeword_models=[config.WAKE_WORD_MODEL], inference_framework="onnx")


def wait_for_wake_word(stream):
    """Blocks until the wake word is heard in WAKE_CONSECUTIVE_FRAMES frames in a row.
    Requiring a few frames filters out one-off spikes from TV, music or coughs."""
    _model.reset()
    hits = 0
    while True:
        data, _ = stream.read(CHUNK)
        scores = _model.predict(data[:, 0])
        score = max(scores.values())
        if config.WAKE_DEBUG and score > 0.1:
            print(f"[wake] score {score:.2f}")
        if score > config.WAKE_THRESHOLD:
            hits += 1
            if hits >= config.WAKE_CONSECUTIVE_FRAMES:
                _model.reset()
                return
        else:
            hits = 0
