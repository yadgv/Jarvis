"""Start Jarvis when you log in to Windows.

    python autostart.py on       start the widget at every login
    python autostart.py off      stop doing that
    python autostart.py          show whether it's on

It puts a small Jarvis.vbs file in your Startup folder that runs gui.py with
pythonw (no console window). Turning it off just deletes that file. You can
also untick "Start with Windows" in the widget's right-click menu, or turn it
off in Task Manager > Startup apps.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "Jarvis.vbs"


def startup_folder() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def shortcut_path() -> str:
    return os.path.join(startup_folder(), NAME)


def windowless_python(exe: str = None) -> str:
    """pythonw.exe (no console) next to the Python running now, if there is one."""
    exe = exe or sys.executable
    folder, name = os.path.split(exe)
    if "pythonw" not in name.lower():
        candidate = os.path.join(folder, name.lower().replace("python", "pythonw", 1))
        if os.path.exists(candidate):
            return candidate
    return exe


def script(python: str = None) -> str:
    python = python or windowless_python()
    gui = os.path.join(HERE, "gui.py")
    return (
        "' Starts Jarvis at login. Delete this file (or run: python autostart.py off) to stop.\r\n"
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.CurrentDirectory = "{HERE}"\r\n'
        f'sh.Run """{python}"" ""{gui}""", 0, False\r\n'
    )


def is_on() -> bool:
    return os.path.exists(shortcut_path())


def turn_on() -> str:
    if sys.platform != "win32":
        return "Starting with the computer only works on Windows."
    os.makedirs(startup_folder(), exist_ok=True)
    with open(shortcut_path(), "w", encoding="utf-8") as f:
        f.write(script())
    return "Jarvis will now start when you log in to Windows."


def turn_off() -> str:
    if is_on():
        os.remove(shortcut_path())
    return "Jarvis won't start automatically any more."


def set_on(on: bool) -> str:
    return turn_on() if on else turn_off()


if __name__ == "__main__":
    arg = (sys.argv[1:] or ["status"])[0].lower()
    if arg in ("on", "enable", "install"):
        print(turn_on())
    elif arg in ("off", "disable", "uninstall", "remove"):
        print(turn_off())
    else:
        print(f"Start with Windows is {'ON' if is_on() else 'OFF'} ({shortcut_path()})")
