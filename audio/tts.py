"""Text-to-speech.
Order: Fish Audio voice (online) -> Piper 'Alan' (local) -> pyttsx3 (system voice).
If Fish Audio fails (no internet, bad key, out of credits) it drops to the next one.
"""
import io
import os
import wave

import numpy as np
import requests
import sounddevice as sd

import config

# ---------- Fish Audio ----------
FISH_URL = "https://api.fish.audio/v1/tts"
FISH_RATE = 44100
_fish_ok = bool(config.FISH_API_KEY and config.FISH_VOICE_ID)


def _speak_fish(text: str) -> bool:
    global _fish_ok
    try:
        r = requests.post(
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
            return False
        r.raise_for_status()
        audio = np.frombuffer(r.content, dtype=np.int16)
        if audio.size == 0:
            return False
        sd.play(audio, FISH_RATE)
        sd.wait()
        return True
    except Exception as e:
        print(f"[tts] Fish Audio failed ({e}) -> using fallback.")
        return False


# ---------- Piper (local) ----------
_piper = None
if os.path.exists(config.PIPER_VOICE):
    try:
        from piper import PiperVoice
        _piper = PiperVoice.load(config.PIPER_VOICE)
    except Exception as e:
        print(f"[tts] Piper failed to load ({e}).")


def _speak_piper(text: str) -> bool:
    if _piper is None:
        return False
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            _piper.synthesize_wav(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        sd.play(audio, rate)
        sd.wait()
        return True
    except Exception as e:
        print(f"[tts] Piper failed ({e}).")
        return False


# ---------- pyttsx3 (last resort) ----------
_fallback = None


def _speak_system(text: str):
    global _fallback
    if _fallback is None:
        import pyttsx3
        _fallback = pyttsx3.init()
        _fallback.setProperty("rate", 175)
    _fallback.say(text)
    _fallback.runAndWait()


def speak(text: str):
    if not text:
        return
    if _fish_ok and _speak_fish(text):
        return
    if _speak_piper(text):
        return
    _speak_system(text)
