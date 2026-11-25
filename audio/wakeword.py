"""Listens for "Hey Jarvis" using openWakeWord (free, runs on the Pi)."""
import os

import openwakeword
from openwakeword.model import Model

import config
from audio.recorder import CHUNK

openwakeword.utils.download_models()  # one-time download (also the voice detector), cached after


def _options():
    """Extra checks openWakeWord has built in (github.com/dscripka/openWakeWord):
    - vad_threshold: a Silero voice detector must also hear speech, so TV, music
      and noise that happen to score high don't wake him.
    - Speex noise suppression (Linux/Pi, needs speexdsp-ns).
    - custom_verifier_models: a small model trained on *your* voice
      (python train_my_voice.py), so other people saying "Hey Jarvis" don't."""
    opts = {"wakeword_models": [config.WAKE_WORD_MODEL], "inference_framework": "onnx"}
    if config.WAKE_VAD_THRESHOLD:
        opts["vad_threshold"] = config.WAKE_VAD_THRESHOLD
    if config.WAKE_NOISE_SUPPRESSION:
        try:
            import speexdsp_ns  # noqa: F401
            opts["enable_speex_noise_suppression"] = True
        except ImportError:
            print("[wake] noise suppression needs: pip install speexdsp-ns (Linux only)")
    return opts


def _load():
    # Fresh options for each Model: openWakeWord rewrites the model list in place.
    model = Model(**_options())
    if config.WAKE_VERIFIER and os.path.exists(config.WAKE_VERIFIER):
        try:
            name = next(iter(model.models))  # "hey_jarvis"
            model = Model(**_options(), custom_verifier_models={name: config.WAKE_VERIFIER},
                          custom_verifier_threshold=config.WAKE_VERIFIER_THRESHOLD)
            print("[wake] only waking for your voice (memory/my_voice_verifier.pkl)")
        except Exception as e:  # e.g. scikit-learn missing
            print(f"[wake] couldn't load your-voice check ({e}); waking for anyone")
    return model


_model = _load()


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
