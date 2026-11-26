"""Smart Turn: has he finished talking, or is he just pausing to think?

Uses the Smart Turn v3 model by Daily (github.com/pipecat-ai/smart-turn,
BSD 2-Clause, Copyright (c) 2024-2025 Daily). predict() below follows their
inference.py; Whisper's log-mel features come from faster-whisper (already
installed for speech-to-text) instead of the transformers library.

The model (~8 MB) is downloaded once to memory/. If anything is missing,
is_finished() returns None and the recorder falls back to plain silence."""
import os

import numpy as np

import config

SECONDS = 8  # the model looks at the last 8 seconds
_session = None
_features = None
_failed = False


def _model_path():
    return os.path.join(config.MEMORY_DIR, os.path.basename(config.SMART_TURN_MODEL_URL))


def _download(path):
    import requests
    print("[turn] downloading the Smart Turn model (8 MB, once)...")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    r = requests.get(config.SMART_TURN_MODEL_URL, timeout=60)
    r.raise_for_status()
    with open(path + ".tmp", "wb") as f:
        f.write(r.content)
    os.replace(path + ".tmp", path)


def load(wait=True) -> bool:
    """Loads the model; False (and a printed reason) if it can't.
    wait=False: False straight away if it's still loading in the background
    (that turn just uses the plain pause)."""
    global _session, _features, _failed
    if _session is not None:
        return True
    if not _load_lock.acquire(blocking=wait):
        return False
    try:
        if _session is not None:
            return True
        return _load()
    finally:
        _load_lock.release()


_load_lock = __import__("threading").Lock()


def _load() -> bool:
    global _session, _features, _failed
    if _failed or not config.SMART_TURN:
        return False
    try:
        import onnxruntime as ort
        from faster_whisper.feature_extractor import FeatureExtractor
        path = _model_path()
        if not os.path.exists(path):
            _download(path)
        so = ort.SessionOptions()
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
        _features = FeatureExtractor(chunk_length=SECONDS)
        return True
    except Exception as e:
        _failed = True
        print(f"[turn] Smart Turn unavailable ({e}); using a plain {config.SILENCE_SECONDS}s pause")
        return False


def _prepare(audio: np.ndarray) -> np.ndarray:
    """Last 8 s, zero-padded at the start; then normalised like HF's
    WhisperFeatureExtractor(do_normalize=True)."""
    n = SECONDS * 16000
    audio = audio[-n:].astype(np.float32)
    if len(audio) < n:
        audio = np.pad(audio, (n - len(audio), 0))
    return (audio - audio.mean()) / np.sqrt(audio.var() + 1e-7)


def predict(audio: np.ndarray) -> float:
    """Probability (0-1) that the speech in this float32 16 kHz audio is a finished turn."""
    mel = _features(_prepare(audio), padding=0)[:, : SECONDS * 100]
    if mel.shape[1] < SECONDS * 100:
        mel = np.pad(mel, ((0, 0), (0, SECONDS * 100 - mel.shape[1])))
    out = _session.run(None, {"input_features": mel[None].astype(np.float32)})
    return float(out[0].reshape(-1)[0])


def is_finished(audio: np.ndarray):
    """True/False, or None if the model isn't available."""
    if not load(wait=False):
        return None
    try:
        p = predict(audio)
    except Exception as e:
        print(f"[turn] Smart Turn failed ({e})")
        return None
    print(f"[turn] finished? {p:.2f}")
    return p > 0.5
