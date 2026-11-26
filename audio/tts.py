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


# ---------- the offline voice (Kokoro or Piper, on this PC) ----------
# One setting picks it: OFFLINE_VOICE in config.py, or "use the fable voice
# offline" by voice (saved in settings.json). A name from OFFLINE_VOICES, a
# Kokoro voice id ("bm_daniel") or a Piper voice ("en_GB-alan-medium").
# Hear them all with: python try_voices.py
VOICE_DIR = os.path.dirname(config.PIPER_VOICE)
SAMPLE = "Good evening, sir. All systems are running, and your tea will be ready in five minutes."


def offline_voice():
    """("kokoro" or "piper", voice id) for the chosen offline voice."""
    name = str(settings.get("offline_voice") or "").strip()
    voice = (getattr(config, "OFFLINE_VOICES", {}) or {}).get(name.lower(), name)
    if not voice:
        voice = os.path.basename(config.PIPER_VOICE)[:-5]
    return ("piper" if "-" in voice else "kokoro"), voice


def voice_names():
    return list((getattr(config, "OFFLINE_VOICES", {}) or {}))


def _download(url, path):
    print(f"[tts] downloading {os.path.basename(path)} for the offline voice...")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(path + ".part", "wb") as f:
            for block in r.iter_content(1 << 20):
                f.write(block)
    os.replace(path + ".part", path)


# ---------- Piper ----------
PIPER_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{locale}/{name}/{quality}/{voice}{ext}"
_pipers = {}  # voice -> PiperVoice
_fetching = set()  # downloads already started in the background


def _in_background(key, target, *args):
    if key in _fetching or not getattr(config, "VOICE_DOWNLOADS", True):
        return
    _fetching.add(key)
    threading.Thread(target=target, args=args, daemon=True, name=f"voice-download-{key}").start()


def _piper_path(voice):
    return os.path.join(VOICE_DIR, voice + ".onnx")


def _download_piper(voice):
    """en_GB-alan-medium -> its two files from the Piper voice library."""
    try:
        locale, name, quality = voice.split("-", 2)
        for ext in (".onnx", ".onnx.json"):
            path = os.path.join(VOICE_DIR, voice + ext)
            if not os.path.exists(path):
                _download(PIPER_URL.format(lang=locale.split("_")[0], locale=locale, name=name,
                                           quality=quality, voice=voice, ext=ext), path)
        return True
    except Exception as e:
        print(f"[tts] couldn't download the Piper voice {voice} ({e}).")
        return False


def _load_piper(voice, wait=False):
    if voice in _pipers:
        return _pipers[voice]
    if not os.path.exists(_piper_path(voice)):
        if not wait:
            _in_background(voice, _download_piper, voice)
            return None
        if not _download_piper(voice):
            return None
    try:
        from piper import PiperVoice
        _pipers[voice] = PiperVoice.load(_piper_path(voice))
    except Exception as e:
        print(f"[tts] Piper failed to load {voice} ({e}).")
        _pipers[voice] = None
    return _pipers[voice]


def _piper_options():
    speed = settings.speed()
    if speed == 1.0:
        return {}
    try:
        from piper import SynthesisConfig
        return {"syn_config": SynthesisConfig(length_scale=1.0 / speed)}
    except Exception:
        return {}


def _synth_piper(text: str, voice: str = None, wait=False):
    """The chosen Piper voice, or the PIPER_VOICE fallback when Kokoro is chosen."""
    if voice is None:
        engine, chosen = offline_voice()
        voice = chosen if engine == "piper" else os.path.basename(config.PIPER_VOICE)[:-5]
    model = _load_piper(voice, wait)
    if model is None:
        return None
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            model.synthesize_wav(text, wf, **_piper_options())
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        return audio, rate
    except Exception as e:
        print(f"[tts] Piper failed ({e}).")
        return None


# ---------- Kokoro (sounds the most natural) ----------
# Idea from OpenJarvis (github.com/open-jarvis/OpenJarvis, Apache-2.0), which
# offers Kokoro as its local voice. Uses kokoro-onnx (github.com/thewh1teagle/kokoro-onnx, MIT).
# OFFLINE_VOICE_QUALITY "best" is the full model (about 310 MB, smoother and
# less robotic); "small" is the compressed one (about 90 MB). They download
# into voices/ the first time; until then Piper is used.
KOKORO_DIR = VOICE_DIR
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_MODELS = {"best": "kokoro-v1.0.onnx", "small": "kokoro-v1.0.int8.onnx"}
KOKORO_VOICES = "voices-v1.0.bin"
_kokoro = None
_kokoro_lock = threading.Lock()


def _kokoro_wanted() -> bool:
    return offline_voice()[0] == "kokoro"


def _kokoro_model_names():
    """Model files to use, the chosen quality first."""
    want = getattr(config, "OFFLINE_VOICE_QUALITY", "best")
    first = KOKORO_MODELS.get(want, KOKORO_MODELS["best"])
    return [first] + [m for m in KOKORO_MODELS.values() if m != first]


def _download_kokoro():
    try:
        for name in (_kokoro_model_names()[0], KOKORO_VOICES):
            path = os.path.join(KOKORO_DIR, name)
            if not os.path.exists(path):
                _download(KOKORO_URL + name, path)
        print("[tts] Kokoro voice ready.")
        return True
    except Exception as e:
        print(f"[tts] couldn't download the Kokoro voice ({e}); using Piper.")
        return False


def _load_kokoro():
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    voices = os.path.join(KOKORO_DIR, KOKORO_VOICES)
    models = [os.path.join(KOKORO_DIR, m) for m in _kokoro_model_names()]
    model = next((m for m in models if os.path.exists(m)), None)
    if model is None or not os.path.exists(voices):
        return None
    with _kokoro_lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(model, voices)
            print(f"[tts] offline voice: Kokoro {offline_voice()[1]} ({os.path.basename(model)})")
    return _kokoro


def _synth_kokoro(text: str, voice: str = None):
    if voice is None:
        engine, voice = offline_voice()
        if engine != "kokoro":
            return None
    try:
        model = _load_kokoro()
        if model is None:
            return None
        # bm_/bf_ voices are British, am_/af_ American.
        samples, rate = model.create(text, voice=voice, speed=settings.speed(),
                                     lang="en-gb" if voice.startswith("b") else "en-us")
        audio = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype(np.int16)
        return audio, rate
    except Exception as e:
        print(f"[tts] Kokoro failed ({e}); using Piper.")
        return None


def _synth_local(text: str):
    """The chosen offline voice; Piper if Kokoro isn't ready."""
    return _synth_kokoro(text) or _synth_piper(text)


def preview(name: str, text: str = SAMPLE) -> str:
    """Say a sample in one offline voice (downloading it first if needed),
    whatever voice is chosen now. Returns what happened, for the log or a tool."""
    voice = (getattr(config, "OFFLINE_VOICES", {}) or {}).get(name.lower().strip(), name.strip())
    if "-" in voice:
        clip = _synth_piper(text, voice, wait=True)
    else:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return "Kokoro voices need: pip install kokoro-onnx"
        if _load_kokoro() is None and not (_download_kokoro() and _load_kokoro()):
            return "The Kokoro voice couldn't be downloaded (needs the internet the first time)."
        clip = _synth_kokoro(text, voice)
    if clip is None:
        return f"Couldn't make the voice {name}."
    play(clip)
    return f"Played a sample of the {name} voice."


def _prepare():
    """At startup: fetch the chosen offline voice in the background if it isn't here yet."""
    engine, voice = offline_voice()
    if engine == "kokoro":
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            print("[tts] the offline voice is Kokoro but kokoro-onnx isn't installed: "
                  "pip install kokoro-onnx (using the robotic system voice until then)")
            return
        if not os.path.exists(os.path.join(KOKORO_DIR, _kokoro_model_names()[0])) or \
                not os.path.exists(os.path.join(KOKORO_DIR, KOKORO_VOICES)):
            _in_background("kokoro", _download_kokoro)
    if engine == "piper":
        _load_piper(voice)
    elif os.path.exists(config.PIPER_VOICE):
        _load_piper(os.path.basename(config.PIPER_VOICE)[:-5])  # the fallback, ready to go


_prepare()


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
