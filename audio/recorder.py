"""Records from the mic until you stop talking."""
import numpy as np
import sounddevice as sd

import config

CHUNK = 1280  # 80 ms at 16 kHz (also what openWakeWord expects)
VAD_FRAME = 320  # 20 ms frames for webrtcvad (4 per chunk)

# Voice activity detector: tells speech apart from noise, so quiet talking
# still counts and fans or clicks don't. Falls back to loudness only.
try:
    import webrtcvad
    _vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
except Exception as e:  # not installed / failed to load
    print(f"[mic] voice detector unavailable ({e}); using loudness only.")
    _vad = None

# Minimum loudness for a chunk to count as speech. calibrate() raises it in
# a noisy room. With the voice detector this can be low; without it we use
# the old SILENCE_THRESHOLD.
_threshold = config.MIN_SPEECH_LEVEL if _vad else config.SILENCE_THRESHOLD


def open_stream():
    return sd.InputStream(
        samplerate=config.SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=CHUNK,
        device=config.MIC_DEVICE,
    )


def calibrate(stream, seconds: float = 1.0) -> float:
    """Measure background noise for a moment and set the speech threshold.
    The config value is the minimum; a noisy room pushes it higher."""
    global _threshold
    n = max(1, int(seconds * config.SAMPLE_RATE / CHUNK))
    levels = []
    for _ in range(n):
        data, _ = stream.read(CHUNK)
        levels.append(float(np.abs(data[:, 0]).mean()))
    noise = float(np.median(levels))
    base = config.MIN_SPEECH_LEVEL if _vad else config.SILENCE_THRESHOLD
    _threshold = max(base, noise * config.NOISE_MULTIPLIER)
    print(f"[mic] background noise {noise:.0f}, speech threshold {_threshold:.0f}")
    return _threshold


def is_speech(chunk) -> bool:
    """True if this 80 ms chunk sounds like someone talking."""
    if np.abs(chunk).mean() <= _threshold:
        return False
    if _vad is None:
        return True
    voiced = 0
    for i in range(0, len(chunk) - VAD_FRAME + 1, VAD_FRAME):
        if _vad.is_speech(chunk[i:i + VAD_FRAME].tobytes(), config.SAMPLE_RATE):
            voiced += 1
    return voiced >= 2  # at least 40 ms of the 80 ms chunk is voice


def record_until_silence(stream, start_timeout: float = None) -> np.ndarray:
    """Returns float32 audio in [-1, 1] for Whisper.
    Gives up (returns empty audio) if no speech starts within start_timeout seconds."""
    if start_timeout is None:
        start_timeout = config.LISTEN_TIMEOUT
    frames = []
    silent_chunks = 0
    heard_speech = False
    chunks_per_sec = config.SAMPLE_RATE / CHUNK
    max_silent = int(config.SILENCE_SECONDS * chunks_per_sec)
    max_chunks = int(config.MAX_RECORD_SECONDS * chunks_per_sec)
    startup_limit = int(start_timeout * chunks_per_sec)

    for i in range(max_chunks):
        data, overflowed = stream.read(CHUNK)
        if overflowed:
            print("[mic] input overflow (audio dropped)")
        chunk = data[:, 0]
        frames.append(chunk)
        if is_speech(chunk):
            heard_speech = True
            silent_chunks = 0
        else:
            silent_chunks += 1

        if heard_speech and silent_chunks > max_silent:
            break
        if not heard_speech and i > startup_limit:
            peak = max(float(np.abs(f).mean()) for f in frames)
            print(f"[mic] no speech detected (loudest {peak:.0f}, needed {_threshold:.0f})")
            return np.array([], dtype=np.float32)

    audio = np.concatenate(frames).astype(np.float32) / 32768.0
    return audio


def chime(stream):
    """Short two-tone beep so you know Jarvis is listening.
    The mic is paused while it plays so the beep isn't recorded."""
    if not config.WAKE_CHIME:
        return
    rate = 22050
    t1 = np.linspace(0, 0.07, int(rate * 0.07), endpoint=False)
    t2 = np.linspace(0, 0.09, int(rate * 0.09), endpoint=False)
    tone = np.concatenate([np.sin(2 * np.pi * 880 * t1), np.sin(2 * np.pi * 1320 * t2)])
    fade = np.minimum(1, np.minimum(np.arange(tone.size), np.arange(tone.size)[::-1]) / 200)
    tone = (0.25 * tone * fade).astype(np.float32)
    stream.stop()
    try:
        sd.play(tone, rate)
        sd.wait()
    finally:
        stream.start()
