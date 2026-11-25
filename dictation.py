"""Hold-a-key dictation: hold DICTATION_KEY, talk, let go, and your words are
typed into whatever app you're in. Speech is turned into text on this PC
(faster-whisper, the same as for "Hey Jarvis"); nothing is sent anywhere.

Idea from isair/jarvis and OpenLive's "Dictate" mode.
Needs: pip install pynput pyperclip pyautogui. Set DICTATION_KEY = None to turn off."""
import threading

import numpy as np

import config

_frames = []
_recording = threading.Event()
_stream = None


def _key_matches(key, wanted):
    name = getattr(key, "name", None) or getattr(key, "char", None) or ""
    return str(name).lower() == wanted


def _start():
    import sounddevice as sd
    global _stream
    _frames.clear()

    def callback(data, frames, t, status):
        if _recording.is_set():
            _frames.append(data[:, 0].copy())
    _stream = sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32",
                             device=config.MIC_DEVICE, callback=callback)
    _stream.start()


def _finish():
    global _stream
    if _stream is not None:
        _stream.stop()
        _stream.close()
        _stream = None
    if not _frames:
        return
    audio = np.concatenate(_frames)
    if len(audio) < config.SAMPLE_RATE * 0.3:
        return  # a tap, not dictation
    from audio.stt import transcribe
    text = transcribe(audio)
    print(f"[dictation] {text!r}")
    if text:
        from skills.text_tools import paste_text
        paste_text(text + " ")


def start():
    """Listen for the dictation key in the background (no-op if turned off or missing libraries)."""
    key = (getattr(config, "DICTATION_KEY", None) or "").lower()
    if not key:
        return False
    try:
        from pynput import keyboard
        import pyperclip  # noqa: F401
    except ImportError:
        print("[dictation] needs: pip install pynput pyperclip pyautogui")
        return False

    def on_press(k):
        if _key_matches(k, key) and not _recording.is_set():
            _recording.set()
            try:
                _start()
            except Exception as e:
                _recording.clear()
                print(f"[dictation] mic failed: {e}")

    def on_release(k):
        if _key_matches(k, key) and _recording.is_set():
            _recording.clear()
            threading.Thread(target=_safe_finish, daemon=True).start()

    keyboard.Listener(on_press=on_press, on_release=on_release).start()  # daemon thread
    print(f"[dictation] hold {key.upper()} to dictate into any app")
    return True


def _safe_finish():
    try:
        _finish()
    except Exception as e:
        print(f"[dictation] failed: {e}")
