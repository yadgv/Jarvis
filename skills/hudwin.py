"""Where Jarvis's own windows (whiteboard, 3D viewer, doc workspace) go.

They open wide (16:9, centred) rather than tall, or side by side for a
split screen: his article on the left half, Jarvis's brief on the right.
Windows only; elsewhere the browser decides.
"""
import sys
import threading
import time

DEFAULT_SCREEN = (0, 0, 1920, 1040)
WIDE = 16 / 9


def work_area():
    """(left, top, width, height) of the main screen without the taskbar."""
    if sys.platform != "win32":
        return DEFAULT_SCREEN
    try:
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    return DEFAULT_SCREEN


def wide_rect(area=None, share: float = 0.8):
    """A centred 16:9 window about `share` of the screen wide."""
    x, y, w, h = area or work_area()
    width = int(w * share)
    height = int(width / WIDE)
    if height > h * 0.9:
        height = int(h * 0.9)
        width = int(height * WIDE)
    return x + (w - width) // 2, y + (h - height) // 2, width, height


def half_rect(side: str, area=None):
    """The left or right half of the screen."""
    x, y, w, h = area or work_area()
    half = w // 2
    return (x, y, half, h) if side == "left" else (x + half, y, w - half, h)


def browser_args(link: str, rect) -> list:
    x, y, w, h = rect
    return [f"--app={link}", f"--window-position={x},{y}", f"--window-size={w},{h}"]


def place(user32, hwnd, rect):
    """Move and size a window (restoring it first if it's maximised or minimised)."""
    x, y, w, h = rect
    if user32.IsZoomed(hwnd) or user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    user32.SetWindowPos(hwnd, None, int(x), int(y), int(w), int(h), 0x0004 | 0x0040)   # no z-order change, show


def arrange(title: str, rect=None, pin: bool = True, opacity: int = 100, wait: float = 15.0, label: str = "window"):
    """Once a window with `title` has opened: size it, bring it to the front
    (pinned on top if pin), and make it see-through (opacity %). Runs in the background."""
    if sys.platform != "win32":
        return

    def run():
        from skills import whiteboard
        try:
            user32 = whiteboard._user32()
            end = time.monotonic() + wait
            while time.monotonic() < end:
                hwnd = whiteboard._find_window(user32, title)
                if hwnd:
                    if rect:
                        place(user32, hwnd, rect)
                    whiteboard._raise(user32, hwnd, pin)
                    try:
                        whiteboard._see_through(user32, hwnd, opacity)
                    except Exception as e:
                        print(f"[{label}] couldn't make the window see-through: {e}")
                    return
                time.sleep(0.25)
            print(f"[{label}] couldn't find the window to bring it to the front")
        except Exception as e:
            print(f"[{label}] couldn't arrange the window: {e}")

    threading.Thread(target=run, daemon=True, name=f"{label}-front").start()
