"""Copy the selected text and paste text into whatever app has focus.
Shared by hold-a-key dictation (dictation.py) and edit-by-voice (edit_text.py).
Needs: pip install pyperclip pyautogui"""
import time

_gui = None


def _pyautogui():
    global _gui
    if _gui is None:
        import pyautogui
        pyautogui.FAILSAFE = True
        _gui = pyautogui
    return _gui


def _clip():
    import pyperclip
    return pyperclip


def copy_selection(wait=0.3) -> str:
    """The text selected in the focused app ('' if nothing is selected).
    The clipboard is put back afterwards."""
    clip = _clip()
    old = clip.paste()
    marker = f"__jarvis_{time.time()}__"
    clip.copy(marker)
    _pyautogui().hotkey("ctrl", "c")
    time.sleep(wait)
    text = clip.paste()
    clip.copy(old)
    return "" if text == marker else text


def paste_text(text: str, wait=0.3):
    """Type text into the focused app by pasting it (works for any language
    and is instant), then put the old clipboard back."""
    clip = _clip()
    old = clip.paste()
    clip.copy(text)
    _pyautogui().hotkey("ctrl", "v")
    time.sleep(wait)  # let the app read the clipboard before it's restored
    clip.copy(old)
