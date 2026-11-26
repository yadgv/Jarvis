"""Fast startup: slow parts load in the background, and each step is timed in the log."""
import sys
import threading
import time
import types

import startup


def test_mark_logs_how_long(capsys):
    t = time.perf_counter() - 1.5
    startup.mark("speech recognition loaded", t)
    out = capsys.readouterr().out
    assert out.startswith("[startup] speech recognition loaded in 1.5s (") and "since launch" in out


def test_whisper_loads_in_the_background(monkeypatch):
    """Importing the speech recogniser returns at once; a turn waits only if it's still loading."""
    started, release = threading.Event(), threading.Event()

    class SlowModel:
        def __init__(self, *a, **k):
            started.set()
            release.wait(5)

        def transcribe(self, audio, **k):
            return [types.SimpleNamespace(text=" hello ")], None
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = SlowModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fw)
    monkeypatch.delitem(sys.modules, "audio.stt", raising=False)
    t = time.perf_counter()
    import importlib
    stt = importlib.import_module("audio.stt")
    assert time.perf_counter() - t < 1 and started.wait(2)
    result = []
    worker = threading.Thread(target=lambda: result.append(stt.transcribe([0.0] * 10)))
    worker.start()
    time.sleep(0.2)
    assert not result                    # waiting for the model
    release.set()
    worker.join(5)
    assert result == ["hello"]
    sys.modules.pop("audio.stt", None)


def test_smart_turn_never_blocks_a_turn_while_loading(monkeypatch):
    from audio import smart_turn
    monkeypatch.setattr(smart_turn, "_session", None)
    smart_turn._load_lock.acquire()
    try:
        assert smart_turn.load(wait=False) is False   # still loading: use the plain pause
    finally:
        smart_turn._load_lock.release()
