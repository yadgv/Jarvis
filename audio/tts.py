"""Text-to-speech.
Order: Fish Audio voice (online) -> Piper 'Alan' (local) -> pyttsx3 (system voice).
If Fish Audio fails (no internet, bad key, out of credits) it drops to the next one.
"""
import io
import os
import threading
import time
import wave

import numpy as np
import requests
import sounddevice as sd

import config

# Only one thing talks at a time (e.g. a timer going off while Jarvis is mid-sentence).
_speaking = threading.RLock()

# ---------- Fish Audio ----------
FISH_URL = "https://api.fish.audio/v1/tts"
FISH_RATE = 44100
_http = requests.Session()  # reuses the connection: saves a TLS handshake per sentence
_fish_ok = bool(config.FISH_API_KEY and config.FISH_VOICE_ID)


def _synth_fish(text: str):
    global _fish_ok
    try:
        r = _http.post(
            FISH_URL,
            headers={
                "Authorization": f"Bearer {config.FISH_API_KEY}",
                "Content-Type": "application/json",
                "model": config.FISH_MODEL,
            },
            json={
                "text": text,
                "reference_id": config.FISH_VOICE_ID,
                "format": "pcm",
                "sample_rate": FISH_RATE,
                "latency": "balanced",
            },
            timeout=20,
        )
        if r.status_code in (401, 402):
            # Bad key or no credits: stop trying for this session
            print(f"[tts] Fish Audio {r.status_code}: {r.text[:120]} -> using fallback.")
            _fish_ok = False
            return None
        r.raise_for_status()
        audio = np.frombuffer(r.content, dtype=np.int16)
        if audio.size == 0:
            return None
        return audio, FISH_RATE
    except Exception as e:
        print(f"[tts] Fish Audio failed ({e}) -> using fallback.")
        return None


# ---------- Piper (local) ----------
_piper = None
if os.path.exists(config.PIPER_VOICE):
    try:
        from piper import PiperVoice
        _piper = PiperVoice.load(config.PIPER_VOICE)
    except Exception as e:
        print(f"[tts] Piper failed to load ({e}).")


def _synth_piper(text: str):
    if _piper is None:
        return None
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            _piper.synthesize_wav(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        return audio, rate
    except Exception as e:
        print(f"[tts] Piper failed ({e}).")
        return None


# ---------- pyttsx3 (last resort) ----------
_fallback = None


def speak_system(text: str):
    global _fallback
    if _fallback is None:
        import pyttsx3
        _fallback = pyttsx3.init()
        _fallback.setProperty("rate", 175)
    with _speaking:
        _fallback.say(text)
        _fallback.runAndWait()


def synthesize(text: str):
    """Turn text into audio without playing it. Returns (samples, rate),
    or None if only the system voice is left (it can't render to audio)."""
    if _fish_ok:
        clip = _synth_fish(text)
        if clip is not None:
            return clip
    return _synth_piper(text)


def stop():
    """Cut off whatever is playing right now (used when you interrupt Jarvis)."""
    try:
        sd.stop()
    except Exception:
        pass


_now_playing = None  # (samples, rate, start time) so the window can animate with his voice


def level() -> float:
    """Loudness (0-1) of what Jarvis is saying right now."""
    playing = _now_playing
    if playing is None:
        return 0.0
    audio, rate, started = playing
    i = int((time.perf_counter() - started) * rate)
    window = audio[max(0, i - rate // 40): i + rate // 40]
    if window.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(window.astype(np.float32) ** 2)))
    return min(1.0, rms / 6000)


def play(clip):
    global _now_playing
    audio, rate = clip
    with _speaking:
        sd.play(audio, rate)
        _now_playing = (audio, rate, time.perf_counter())
        try:
            sd.wait()
        finally:
            _now_playing = None


def speak(text: str):
    if not text:
        return
    clip = synthesize(text)
    if clip is not None:
        play(clip)
    else:
        speak_system(text)
