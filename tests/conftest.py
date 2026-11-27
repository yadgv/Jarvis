"""Test setup: stub out audio and API libraries so tests run anywhere,
without a microphone, speakers, models or network."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


def _stub(name, **attrs):
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod


class _Whisper:
    def __init__(self, *a, **k):
        pass

    def transcribe(self, *a, **k):
        return iter([]), None


_stub("sounddevice", play=lambda *a, **k: None, wait=lambda: None, InputStream=object)
_stub("faster_whisper", WhisperModel=_Whisper)
_stub("anthropic", Anthropic=lambda **k: None)

import config  # noqa: E402

config.MODE = "enter"  # main.py then skips loading the wake-word model
config.SMART_TURN = False  # tests that want it patch audio.smart_turn
config.DUCK_APPS = []
config.AUTO_MEMORY = False  # tests that want it turn it on
config.ASK_BEFORE_PAID = False  # tests that want the "use Claude?" question turn it on
config.BACKGROUND_TASKS = False  # tests that want background jobs turn them on
config.OFFLINE_VOICE = "alan"  # Piper: no Kokoro during tests
config.VOICE_DOWNLOADS = False  # and no voice downloads
config.QUICK_COMMANDS = False  # tests that want simple commands done with no model turn it on
config.LOCAL_MODEL = ""  # no Ollama in tests (tests that want it set it)
config.ANSWER_CACHE = False  # and the same for reusing saved answers


import pytest  # noqa: E402
import requests  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never hit real services; a test that needs a response
    patches requests itself."""
    def blocked(*a, **k):
        raise requests.ConnectionError("network disabled in tests")
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests, "post", blocked)
    monkeypatch.setattr(requests.Session, "request", blocked)
    # The internet counts as up unless a test says otherwise (brain/network.py).
    from brain import network
    monkeypatch.setattr(network, "_check", lambda: True)
    monkeypatch.setattr(network, "_state", {"online": None, "until": 0.0})


@pytest.fixture(autouse=True)
def private_whiteboard(monkeypatch, tmp_path):
    """The whiteboard saves its last drawing in memory/; keep tests' drawings out of it."""
    from skills import whiteboard
    monkeypatch.setattr(whiteboard, "_saved_path", lambda: str(tmp_path / "whiteboard.json"))


@pytest.fixture(autouse=True)
def private_files(monkeypatch, tmp_path):
    """File tools only ever see a fake home folder, and keep their undo log there."""
    home = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads"):
        (home / name).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(config, "FILE_FOLDERS", ["Desktop", "Documents", "Downloads"])
    from skills import files
    monkeypatch.setattr(files, "_undo_path", lambda: str(tmp_path / "file_undo.json"))
    monkeypatch.setattr(files, "_plan", None)
    return home


@pytest.fixture(autouse=True)
def no_windows(monkeypatch):
    """Nothing a test does opens a real browser window."""
    from skills import whiteboard
    monkeypatch.setattr(whiteboard, "_app_browser", lambda: None)
    monkeypatch.setattr(whiteboard.webbrowser, "open", lambda *a, **k: True)
    monkeypatch.setattr(whiteboard, "_board", {"version": 0, "title": "", "svg": "", "steps": [], "step": 0,
                                               "topic": "", "spec": None, "closed": False})


@pytest.fixture(autouse=True)
def private_caches(monkeypatch, tmp_path):
    """The token count and saved answers live in memory/; keep tests' ones out of it."""
    from brain import cache, usage
    monkeypatch.setattr(usage, "_path", lambda: str(tmp_path / "token_use.json"))
    monkeypatch.setattr(cache, "_path", lambda: str(tmp_path / "answer_cache.json"))
    monkeypatch.setattr(cache, "_data", None)
