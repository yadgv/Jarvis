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
