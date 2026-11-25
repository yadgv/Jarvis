"""Records from the mic until you stop talking."""
import sys

import numpy as np
import sounddevice as sd

import config
import ui_events
from audio import smart_turn

CHUNK = 1280  # 80 ms at 16 kHz (also what openWakeWord expects)
VAD_FRAME = 320  # 20 ms frames for webrtcvad (4 per chunk)

# Voice activity detector: tells speech apart from noise, so quiet talking
# still counts and fans or clicks don't. Falls back to loudness only.
try:
    import webrtcvad
    _vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
except Exception as e:  # not installed / failed to load
    print(f"[mic] voice detector unavailable ({e}); using loudness only.\n"
          f"      To install it for the Python that runs Jarvis:\n"
          f'      "{sys.executable}" -m pip install webrtcvad-wheels')
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


def record_until_silence(stream, start_timeout: float = None, ignore_seconds: float = 0) -> np.ndarray:
    """Returns float32 audio in [-1, 1] for Whisper.
    Gives up (returns empty audio) if no speech starts within start_timeout seconds.
    The first ignore_seconds (the wake beep) are kept, so words said over the
    beep aren't lost, but don't count as speech.

    With Smart Turn on, a short pause ends your turn only if the model thinks
    you've finished the sentence; a "thinking" pause waits longer.

    Background voices also sound like speech, so once you've started talking
    Jarvis learns how loud *you* are. After that, only sound at least
    SPEAKER_DROP of your level counts as you still talking; quieter chatter
    in the room is treated as silence, so he stops recording when you stop."""
    if start_timeout is None:
        start_timeout = config.LISTEN_TIMEOUT
    frames = []
    silent_chunks = 0
    heard_speech = False
    speaker_level = 0.0
    speech_chunks = 0
    chunks_per_sec = config.SAMPLE_RATE / CHUNK
    max_silent = plain_silent = int(config.SILENCE_SECONDS * chunks_per_sec)
    max_chunks = int(config.MAX_RECORD_SECONDS * chunks_per_sec)
    startup_limit = int(start_timeout * chunks_per_sec)
    skip = int((ignore_seconds or 0) * chunks_per_sec + 0.999)
    smart = smart_turn.load()
    if smart:
        smart_first = max(1, int(config.SMART_TURN_SILENCE * chunks_per_sec))
        smart_every = max(1, int(0.4 * chunks_per_sec))
        max_silent = int(config.SMART_TURN_MAX_SILENCE * chunks_per_sec)
        smart_min_speech = max(1, int(getattr(config, "SMART_TURN_MIN_SPEECH", 0.5) * chunks_per_sec))
    ended = "time limit"

    for i in range(max_chunks):
        data, overflowed = stream.read(CHUNK)
        if overflowed:
            print("[mic] input overflow (audio dropped)")
        chunk = data[:, 0]
        frames.append(chunk)
        loudness = float(np.abs(chunk).mean())
        ui_events.emit("level", min(1.0, loudness / 1500))

        talking = i >= skip and is_speech(chunk)
        if talking and heard_speech and loudness < speaker_level * config.SPEAKER_DROP:
            talking = False  # someone quieter in the background, not you
        if talking:
            heard_speech = True
            silent_chunks = 0
            speech_chunks += 1
            if speech_chunks <= 15:  # learn your level from your first ~1.2 s of speech
                speaker_level = max(speaker_level * 0.9, loudness) if speech_chunks > 1 else loudness * 0.8
        else:
            silent_chunks += 1

        if heard_speech and silent_chunks > max_silent:
            ended = "pause"
            break
        # Smart Turn may only end the turn after real speech (~0.5 s): on a
        # blip (the end of the beep, a tap) it says "finished" at once, which
        # cut recordings off at 1 s before he'd started talking.
        if (smart and speech_chunks >= smart_min_speech and silent_chunks >= smart_first
                and (silent_chunks - smart_first) % smart_every == 0):
            audio = np.concatenate(frames).astype(np.float32) / 32768.0
            finished = smart_turn.is_finished(audio)
            if finished is None:  # model failed: back to a plain pause
                smart, max_silent = False, plain_silent
            elif finished:
                ended = "finished sentence"
                break
        if not heard_speech and i > startup_limit:
            peak = max(float(np.abs(f).mean()) for f in frames)
            print(f"[mic] no speech detected (loudest {peak:.0f}, needed {_threshold:.0f})")
            return np.array([], dtype=np.float32)

    audio = np.concatenate(frames).astype(np.float32) / 32768.0
    print(f"[mic] recorded {len(audio) / config.SAMPLE_RATE:.1f}s, ended by {ended} "
          f"(your level {speaker_level:.0f}, background below {speaker_level * config.SPEAKER_DROP:.0f} ignored)")
    return audio


def chime(stream) -> float:
    """Short two-tone beep so you know Jarvis is listening. Returns its length.
    The mic keeps running (like GLaDOS and Home Assistant's pre-roll buffer),
    so "Hey Jarvis, what's the weather" said in one go isn't cut; the
    recorder just doesn't count the beep as speech."""
    if not config.WAKE_CHIME:
        return 0.0
    rate = 22050
    t1 = np.linspace(0, 0.07, int(rate * 0.07), endpoint=False)
    t2 = np.linspace(0, 0.09, int(rate * 0.09), endpoint=False)
    tone = np.concatenate([np.sin(2 * np.pi * 880 * t1), np.sin(2 * np.pi * 1320 * t2)])
    fade = np.minimum(1, np.minimum(np.arange(tone.size), np.arange(tone.size)[::-1]) / 200)
    tone = (0.25 * tone * fade).astype(np.float32)
    sd.play(tone, rate)  # doesn't wait: recording starts straight away
    return tone.size / rate + 0.1  # plus a little for the speaker's delay
