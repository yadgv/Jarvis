"""Text-to-speech.
Order: Fish Audio voice (online) -> Piper 'Alan' (local) -> pyttsx3 (system voice).
If Fish Audio fails (no internet, bad key, out of credits) it drops to the next one.

Fish Audio is streamed: synthesize() starts downloading straight away in the
background, and play() starts the speakers on the first few hundred
milliseconds of audio instead of waiting for the whole sentence.
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
from brain import network, settings

# Only one thing talks at a time (e.g. a timer going off while Jarvis is mid-sentence).
_speaking = threading.RLock()

# ---------- Fish Audio ----------
FISH_URL = "https://api.fish.audio/v1/tts"
FISH_RATE = 44100
_http = requests.Session()  # reuses the connection: saves a TLS handshake per sentence
_fish_ok = bool(config.FISH_API_KEY and config.FISH_VOICE_ID)


def _fish_request(text: str, stream: bool):
    return _http.post(
            FISH_URL,
            headers={
                "Authorization": f"Bearer {config.FISH_API_KEY}",
                "Content-Type": "application/json",
                "model": config.FISH_MODEL,
            },
            json={
                "text": text,
                "reference_id": settings.voice_id(),
                "format": "pcm",
                "sample_rate": FISH_RATE,
                "latency": "balanced",
                "prosody": {"speed": settings.speed(), "volume": 0},
            },
            timeout=20,
            stream=stream,
        )


def _synth_fish(text: str):
    global _fish_ok
    try:
        r = _fish_request(text, stream=False)
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


def _piper_options():
    speed = settings.speed()
    if speed == 1.0:
        return {}
    try:
        from piper import SynthesisConfig
        return {"syn_config": SynthesisConfig(length_scale=1.0 / speed)}
    except Exception:
        return {}


def _synth_piper(text: str):
    if _piper is None:
        return None
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            _piper.synthesize_wav(text, wf, **_piper_options())
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        return audio, rate
    except Exception as e:
        print(f"[tts] Piper failed ({e}).")
        return None


# ---------- Kokoro (local, better-sounding backup) ----------
# Idea from OpenJarvis (github.com/open-jarvis/OpenJarvis, Apache-2.0), which
# offers Kokoro as its local voice. Uses kokoro-onnx (github.com/thewh1teagle/kokoro-onnx, MIT).
# The two model files (about 120 MB) download into voices/ in the background the
# first time; until then Piper is used.
KOKORO_DIR = os.path.dirname(config.PIPER_VOICE)
KOKORO_FILES = {
    "kokoro-v1.0.int8.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
_kokoro = None
_kokoro_lock = threading.Lock()


def _kokoro_wanted() -> bool:
    return getattr(config, "LOCAL_VOICE", "piper") == "kokoro"


def _download_kokoro():
    try:
        os.makedirs(KOKORO_DIR, exist_ok=True)
        for name, url in KOKORO_FILES.items():
            path = os.path.join(KOKORO_DIR, name)
            if os.path.exists(path):
                continue
            print(f"[tts] downloading {name} for the Kokoro voice...")
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(path + ".part", "wb") as f:
                    for block in r.iter_content(1 << 20):
                        f.write(block)
            os.replace(path + ".part", path)
        print("[tts] Kokoro voice ready.")
    except Exception as e:
        print(f"[tts] couldn't download the Kokoro voice ({e}); using Piper.")


def _load_kokoro():
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    paths = [os.path.join(KOKORO_DIR, n) for n in KOKORO_FILES]
    if not all(os.path.exists(p) for p in paths):
        return None
    with _kokoro_lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(*paths)
    return _kokoro


def _synth_kokoro(text: str):
    if not _kokoro_wanted():
        return None
    try:
        model = _load_kokoro()
        if model is None:
            return None
        samples, rate = model.create(text, voice=getattr(config, "KOKORO_VOICE", "bm_george"),
                                     speed=settings.speed(), lang="en-gb")
        audio = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype(np.int16)
        return audio, rate
    except Exception as e:
        print(f"[tts] Kokoro failed ({e}); using Piper.")
        return None


def _synth_local(text: str):
    """Best voice that runs on this PC: Kokoro if set up, else Piper."""
    return _synth_kokoro(text) or _synth_piper(text)


if _kokoro_wanted():
    try:
        import kokoro_onnx  # noqa: F401
        if not all(os.path.exists(os.path.join(KOKORO_DIR, n)) for n in KOKORO_FILES):
            threading.Thread(target=_download_kokoro, daemon=True, name="kokoro-download").start()
    except ImportError:
        print("[tts] LOCAL_VOICE is kokoro but kokoro-onnx isn't installed: pip install kokoro-onnx")


# ---------- pyttsx3 (last resort) ----------
_fallback = None


def speak_system(text: str):
    global _fallback
    if _fallback is None:
        import pyttsx3
        _fallback = pyttsx3.init()
        _fallback.setProperty("rate", int(175 * settings.speed()))
    with _speaking:
        _fallback.say(text)
        _fallback.runAndWait()


class StreamClip:
    """Audio that is still arriving. Starts downloading the moment it's made,
    so the next sentence loads while the current one plays. If Fish Audio
    fails before sending any audio, it quietly switches to Piper."""

    def __init__(self, text: str):
        self.text = text
        self.rate = FISH_RATE
        self.chunks = []              # int16 arrays, in order
        self.done = threading.Event()
        self.arrived = threading.Condition()
        self.failed = False           # nothing playable at all (use the system voice)
        self.created = time.perf_counter()
        threading.Thread(target=self._fetch, daemon=True).start()

    def _add(self, samples):
        with self.arrived:
            self.chunks.append(samples)
            self.arrived.notify_all()

    def _fetch(self):
        global _fish_ok
        got_audio = False
        try:
            r = _fish_request(self.text, stream=True)
            if r.status_code in (401, 402):
                print(f"[tts] Fish Audio {r.status_code}: {r.text[:120]} -> using fallback.")
                _fish_ok = False
                raise RuntimeError("no Fish Audio")
            r.raise_for_status()
            spare = b""
            for data in r.iter_content(chunk_size=4096):
                data = spare + data
                cut = len(data) - len(data) % 2      # whole 16-bit samples only
                spare = data[cut:]
                if cut:
                    got_audio = True
                    self._add(np.frombuffer(data[:cut], dtype=np.int16))
        except Exception as e:
            if not got_audio:
                if str(e) != "no Fish Audio":
                    print(f"[tts] Fish Audio failed ({e}) -> using fallback.")
                clip = _synth_local(self.text)
                if clip is None:
                    self.failed = True
                else:
                    self.rate = clip[1]
                    self._add(clip[0])
            else:
                print(f"[tts] Fish Audio stream cut off ({e}).")
        finally:
            if not got_audio and not self.chunks:
                self.failed = True
            with self.arrived:
                self.done.set()
                self.arrived.notify_all()

    def wait_start(self, timeout=20) -> bool:
        """Wait until the first audio (or the end) arrives. False = no audio."""
        with self.arrived:
            self.arrived.wait_for(lambda: self.chunks or self.done.is_set(), timeout)
        return bool(self.chunks)

    def next_chunk(self, i):
        """Chunk number i, waiting for it if it hasn't arrived yet; None at the end."""
        with self.arrived:
            self.arrived.wait_for(lambda: len(self.chunks) > i or self.done.is_set(), 20)
            return self.chunks[i] if len(self.chunks) > i else None


def synthesize(text: str):
    """Start turning text into audio without playing it. Returns something
    play() understands, or None if only the system voice is left (it can't
    render to audio)."""
    if _fish_ok and network.online():
        return StreamClip(text)
    return _synth_local(text)


_stop = threading.Event()


def stop():
    """Cut off whatever is playing right now (used when you interrupt Jarvis)."""
    _stop.set()
    try:
        sd.stop()
    except Exception:
        pass


_now_playing = None  # (samples, rate, start time) so the window can animate with his voice


_stream_level = None  # loudness of the streamed audio being played, if any


def level() -> float:
    """Loudness (0-1) of what Jarvis is saying right now."""
    if _stream_level is not None:
        return _stream_level
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


def _play_stream(clip: StreamClip) -> bool:
    """Play audio while it's still downloading. False if there was none."""
    global _stream_level
    if not clip.wait_start():
        return False
    waited = time.perf_counter() - clip.created
    block = clip.rate // 40   # 25 ms pieces, so the orb follows the voice
    with _speaking:
        _stop.clear()
        print(f"[time] voice started {waited:.2f}s after the text was ready")
        try:
            with sd.OutputStream(samplerate=clip.rate, channels=1, dtype="int16") as out:
                i = 0
                while not _stop.is_set():
                    chunk = clip.next_chunk(i)
                    if chunk is None:
                        break
                    i += 1
                    for start in range(0, len(chunk), block):
                        if _stop.is_set():
                            break
                        piece = chunk[start:start + block]
                        _stream_level = min(1.0, float(np.sqrt(np.mean(piece.astype(np.float32) ** 2))) / 6000)
                        out.write(piece.reshape(-1, 1))
        finally:
            _stream_level = None
    return True


def play(clip):
    global _now_playing
    if isinstance(clip, StreamClip):
        if not _play_stream(clip) and not _stop.is_set():
            speak_system(clip.text)
        return
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
