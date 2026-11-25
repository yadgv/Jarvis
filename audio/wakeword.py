"""Listens for "Hey Jarvis" using openWakeWord (free, runs on the Pi)."""
import openwakeword
from openwakeword.model import Model

import config
from audio.recorder import CHUNK

openwakeword.utils.download_models()  # one-time download, cached after
_model = Model(wakeword_models=[config.WAKE_WORD_MODEL], inference_framework="onnx")


def wait_for_wake_word(stream, poll=None):
    """Blocks until the wake word is heard in WAKE_CONSECUTIVE_FRAMES frames in a row.
    Requiring a few frames filters out one-off spikes from TV, music or coughs.
    If poll() returns something (e.g. a message typed in the window), returns that."""
    _model.reset()
    hits = 0
    while True:
        if poll is not None:
            request = poll()
            if request:
                return request
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


def watch_for_interrupt(stream, stop_event, on_wake):
    """While Jarvis is talking: listen for "Hey Jarvis" and call on_wake() if heard.
    Uses a stricter threshold than normal, because the mic also picks up
    Jarvis's own voice from the speaker. Returns when stop_event is set."""
    _model.reset()
    hits = 0
    while not stop_event.is_set():
        data, _ = stream.read(CHUNK)
        score = max(_model.predict(data[:, 0]).values())
        if score > config.BARGE_IN_THRESHOLD:
            hits += 1
            if hits >= config.WAKE_CONSECUTIVE_FRAMES + 1:
                _model.reset()
                on_wake()
                return
        else:
            hits = 0
