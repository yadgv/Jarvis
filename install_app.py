"""Make Jarvis an app you can open: a "Jarvis" shortcut on the Desktop and in
the Start menu, with the orb as its icon. It opens the widget (gui.py) with no
console window; everything that would have printed goes to jarvis.log.

    python install_app.py            add the shortcuts (asks about starting at login)
    python install_app.py --login    ...and start Jarvis when you log in too
    python install_app.py remove     take the shortcuts away

Run it once with the same Python you run Jarvis with (python3.13 on this PC).
Pin it to the taskbar by right-clicking the Start menu entry.
"""
import os
import subprocess
import sys

import autostart

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "jarvis.ico")
NAME = "Jarvis.lnk"

# Makes one .lnk with Windows' own shortcut maker. Values come in through
# environment variables, so paths with spaces or quotes need no escaping.
_PS = r"""
$dir = $env:J_DIR
if ($dir -eq 'DESKTOP') { $dir = [Environment]::GetFolderPath('Desktop') }
$path = Join-Path $dir $env:J_NAME
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$s.TargetPath = $env:J_TARGET
$s.Arguments = $env:J_ARGS
$s.WorkingDirectory = $env:J_WORKDIR
$s.IconLocation = $env:J_ICON
$s.Description = 'Jarvis, your voice assistant'
$s.Save()
Write-Output $path
"""


def start_menu_folder() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")


def desktop_folder() -> str:
    """Where the Desktop is (OneDrive moves it on many PCs)."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def make_icon(path: str = ICON) -> str:
    """Draw the orb (a glowing silver-blue sphere) as a Windows icon."""
    from PIL import Image, ImageDraw, ImageFilter
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((28, 28, 228, 228), fill=(90, 170, 255, 170))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
    orb = ImageDraw.Draw(img)
    centre, radius = 128, 92
    for r in range(radius, 0, -1):  # bright centre fading out to blue
        t = r / radius
        colour = (int(235 - 150 * t), int(245 - 95 * t), 255, 255)
        orb.ellipse((centre - r, centre - r, centre + r, centre + r), fill=colour)
    orb.ellipse((centre - radius, centre - radius, centre + radius, centre + radius),
                outline=(200, 230, 255, 255), width=4)
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def shortcut_values(python: str = None) -> dict:
    return {
        "J_TARGET": python or autostart.windowless_python(),
        "J_ARGS": f'"{os.path.join(HERE, "gui.py")}"',
        "J_WORKDIR": HERE,
        "J_ICON": ICON,
        "J_NAME": NAME,
    }


def make_shortcut(folder: str) -> str:
    env = dict(os.environ, J_DIR=folder, **shortcut_values())
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS],
                         env=env, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "PowerShell couldn't make the shortcut")
    return out.stdout.strip()


def install(login=None) -> list:
    if sys.platform != "win32":
        return ["The Jarvis app shortcut is for Windows. On the Pi, use deploy/install_pi.sh."]
    lines = []
    if not os.path.exists(ICON):
        try:
            make_icon()
        except Exception as e:
            lines.append(f"(Couldn't draw the orb icon: {e}. The shortcut gets Python's icon.)")
    for folder in ("DESKTOP", start_menu_folder()):
        lines.append(f"Made {make_shortcut(folder)}")
    if login is None:
        try:
            login = input("Start Jarvis when you log in to Windows? [y/N] ").strip().lower().startswith("y")
        except EOFError:
            login = False
    if login:
        lines.append(autostart.turn_on())
    lines.append("Done. Open Jarvis from the Desktop or the Start menu; the log is in jarvis.log.")
    return lines


def remove() -> list:
    lines = []
    for folder in (desktop_folder(), start_menu_folder()):
        path = os.path.join(folder, NAME)
        if os.path.exists(path):
            os.remove(path)
            lines.append(f"Removed {path}")
    return lines + ["The Jarvis shortcuts are gone (starting at login is unchanged: python autostart.py off)."]


if __name__ == "__main__":
    args = [a.lower() for a in sys.argv[1:]]
    if "remove" in args or "uninstall" in args:
        result = remove()
    else:
        result = install(login=True if "--login" in args else (False if "--no-login" in args else None))
    print("\n".join(result))
