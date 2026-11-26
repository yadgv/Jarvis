"""Listens for "Hey Jarvis" using openWakeWord (free, runs on the Pi),
and for just "Jarvis" (WAKE_ON_NAME) with a two-step check: a short word said
on its own, with a pause before and after, is transcribed locally and wakes
him only if it was his name. Ordinary talking never gets transcribed."""
import collections
import os
import re

import numpy as np
import openwakeword
from openwakeword.model import Model

import config
from audio.recorder import CHUNK, is_speech

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


# "Third person in the room" (off by default, config.ROOM_CONTEXT): keep the
# last minute of sound heard while waiting, in memory only, so "Jarvis, what
# do you think?" can use what was just being discussed. Idea from isair/jarvis.
_room = collections.deque(maxlen=max(1, int(getattr(config, "ROOM_CONTEXT_SECONDS", 60) * 16000 / CHUNK)))
WAKE_TAIL_CHUNKS = 20  # ~1.6 s: the "Hey Jarvis" itself, left out


def take_room_audio():
    """The audio heard before the wake word (float32), then forgets it."""
    chunks = list(_room)[:-WAKE_TAIL_CHUNKS]
    _room.clear()
    if not chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


NAME = re.compile(r"^(?:(?:hey|hi|ok|okay|yo|oi)[ ,]+)?(?:jarvis|jervis|jarvas|javis|jarvi|jarves)$")


def is_name(text: str) -> bool:
    """True if the transcript is just his name ("Jarvis", "Jarvis?", "Hey Jarvis.")."""
    words = re.sub(r"[^a-z ,]", "", (text or "").lower()).strip(" ,")
    return bool(NAME.match(words))


class NameSpotter:
    """Finds short words said on their own (pause, a word, pause), the shape of
    someone calling "Jarvis". Feed it every 80 ms chunk; it returns that
    word's audio (int16) when one ends, else None."""
    def __init__(self):
        sec = 16000 / CHUNK  # chunks per second
        self.min_chunks = max(1, int(config.NAME_MIN_SECONDS * sec))
        self.max_chunks = max(self.min_chunks, int(config.NAME_MAX_SECONDS * sec))
        self.quiet_after = max(1, int(config.NAME_PAUSE_SECONDS * sec))
        self.quiet_before = max(1, int(config.NAME_PAUSE_SECONDS * sec))
        self.reset()

    def reset(self):
        self.speech, self.silence, self.quiet_run, self.too_long = [], 0, self.quiet_before, False
        self.last = self.pad = None

    def feed(self, chunk, speaking: bool):
        if speaking:
            if not self.speech:
                if self.quiet_run < self.quiet_before:  # no pause before it: part of a sentence
                    self.too_long = True
                self.pad = self.last
            self.speech.append(chunk)
            self.silence = 0
            if len(self.speech) > self.max_chunks:
                self.too_long = True
            self.quiet_run = 0
            self.last = chunk
            return None
        self.quiet_run += 1
        self.last = chunk
        if not self.speech:
            return None
        self.silence += 1
        self.speech.append(chunk)  # keep the word's tail
        if self.silence < self.quiet_after:
            return None
        word = self.speech[:-self.silence + 1] if self.silence > 1 else self.speech
        spoken = len(self.speech) - self.silence
        ok = not self.too_long and spoken >= self.min_chunks
        pad = self.pad
        self.speech, self.silence, self.too_long = [], 0, False
        if not ok:
            return None
        return np.concatenate(([pad] if pad is not None else []) + word)


def _heard_name(audio) -> bool:
    from audio.stt import transcribe
    text = transcribe(audio.astype(np.float32) / 32768.0)
    if config.WAKE_DEBUG or text:
        print(f"[wake] short word heard: {text!r}")
    return is_name(text)


def wait_for_wake_word(stream, poll=None):
    """Blocks until the wake word is heard in WAKE_CONSECUTIVE_FRAMES frames in a row.
    Requiring a few frames filters out one-off spikes from TV, music or coughs.
    If poll() returns something (e.g. a message typed in the window), returns that."""
    _model.reset()
    hits = 0
    spotter = NameSpotter() if config.WAKE_ON_NAME else None
    while True:
        if poll is not None:
            request = poll()
            if request:
                return request
        data, _ = stream.read(CHUNK)
        if config.ROOM_CONTEXT:
            _room.append(data[:, 0].copy())
        if spotter is not None:
            word = spotter.feed(data[:, 0].copy(), is_speech(data[:, 0]))
            if word is not None and _heard_name(word):
                print("[wake] heard his name")
                _model.reset()
                return
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
