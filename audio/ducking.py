"""Turns music down while Jarvis listens and talks, then back up.

Idea from Home Assistant's linux-voice-assistant (github.com/OHF-Voice/
linux-voice-assistant, Apache-2.0), which ducks its media player during a
conversation. On Windows each app has its own volume in the mixer; pycaw
(pip install pycaw) sets it for the apps in config.DUCK_APPS only, so
Jarvis's own voice stays at full volume. Elsewhere this does nothing."""
import sys
import threading

import config

_lock = threading.Lock()
_saved = {}  # process name -> (volume control, volume before ducking)
_warned = False


def _sessions():
    global _warned
    if sys.platform != "win32" or not config.DUCK_APPS:
        return []
    try:
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetAllSessions()
    except Exception as e:
        if not _warned:
            _warned = True
            print(f"[duck] can't turn music down ({e}). To enable: pip install pycaw")
        return []


def duck():
    """Lower the listed apps' volume (does nothing if already ducked)."""
    wanted = {n.lower() for n in config.DUCK_APPS}
    with _lock:
        if _saved:
            return
        try:
            for s in _sessions():
                name = s.Process.name() if s.Process else ""
                if name.lower() not in wanted:
                    continue
                vol = s.SimpleAudioVolume
                level = vol.GetMasterVolume()
                _saved[f"{name}:{s.ProcessId}"] = (vol, level)
                vol.SetMasterVolume(level * config.DUCK_VOLUME, None)
        except Exception as e:
            print(f"[duck] {e}")


def restore():
    """Put the volumes back the way they were."""
    with _lock:
        for vol, level in _saved.values():
            try:
                vol.SetMasterVolume(level, None)
            except Exception:
                pass  # the app was closed meanwhile
        _saved.clear()
