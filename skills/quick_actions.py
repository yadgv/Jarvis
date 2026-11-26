"""Tier 1 of PC control: do it directly, with no screenshots and no big model.

Settings pages open by their ms-settings: link, dark mode flips a registry
value, websites and searches open as links, folders open in Explorer. Each of
these is one cheap tool call instead of a screen-control task that sends
several screenshots to the bigger model. Only fixed, known actions are here;
nothing runs an arbitrary command.

The tiers (see also skills/ui_automation.py and skills/computer.py):
  1. these direct actions
  2. app_controls: read an app's buttons as text and click them by name
  3. use_computer: screenshots, only when 1 and 2 can't do it
"""
import os
import subprocess
import sys
import urllib.parse
import webbrowser

IS_WINDOWS = sys.platform == "win32"

# Browsers he can name ("pull it up on Brave"). Paths are the usual Windows installs.
BROWSERS = {
    "brave": [r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
              r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
              r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"],
    "chrome": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
               r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
               r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
    "edge": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
             r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"],
    "firefox": [r"%ProgramFiles%\Mozilla Firefox\firefox.exe", r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"],
}
_BROWSER_NAMES = {"brave": "brave", "brave browser": "brave", "the brave browser": "brave", "brave web browser": "brave",
                  "braves": "brave", "chrome": "chrome", "google chrome": "chrome", "edge": "edge",
                  "microsoft edge": "edge", "firefox": "firefox", "mozilla firefox": "firefox"}


def browser_key(name: str) -> str:
    """'Brave browser', 'on brave' -> 'brave'; '' if it isn't a browser he named."""
    n = " ".join((name or "").lower().replace("-", " ").split())
    n = n[3:] if n.startswith("on ") else n
    return _BROWSER_NAMES.get(n) or _BROWSER_NAMES.get(n.removesuffix(" browser"), "")


def browser_path(key: str) -> str:
    """The browser's .exe, or ''."""
    import shutil
    for p in BROWSERS.get(key, []):
        p = os.path.expandvars(p)
        if os.path.isfile(p):
            return p
    return shutil.which({"brave": "brave", "chrome": "chrome", "edge": "msedge", "firefox": "firefox"}.get(key, key)) or ""


def open_url(url: str, browser: str = "") -> str:
    """Open a link in the browser he named, else config.BROWSER, else his default browser. Returns which."""
    import config
    key = browser_key(browser) or browser_key(getattr(config, "BROWSER", "") or "")
    exe = browser_path(key) if key else ""
    if exe:
        subprocess.Popen([exe, url] if url else [exe])
        return key.title()
    webbrowser.open(url)
    return ""

SETTINGS = {
    "display": "display", "screen": "display", "brightness": "display", "night light": "nightlight",
    "sound": "sound", "audio": "sound", "bluetooth": "bluetooth", "wifi": "network-wifi",
    "wi-fi": "network-wifi", "network": "network", "vpn": "network-vpn", "airplane mode": "network-airplanemode",
    "dark mode": "colors", "colours": "colors", "colors": "colors", "personalization": "personalization",
    "wallpaper": "personalization-background", "background": "personalization-background",
    "lock screen": "lockscreen", "themes": "themes", "taskbar": "taskbar", "notifications": "notifications",
    "focus": "quiethours", "do not disturb": "quiethours", "power": "powersleep", "sleep": "powersleep",
    "battery": "batterysaver", "storage": "storagesense", "apps": "appsfeatures",
    "default apps": "defaultapps", "startup apps": "startupapps", "windows update": "windowsupdate",
    "updates": "windowsupdate", "mouse": "mousetouchpad", "touchpad": "devices-touchpad",
    "keyboard": "keyboard", "printers": "printers", "devices": "devices", "accounts": "yourinfo",
    "sign in options": "signinoptions", "privacy": "privacy", "microphone": "privacy-microphone",
    "camera": "privacy-webcam", "location": "privacy-location", "time": "dateandtime",
    "date and time": "dateandtime", "language": "regionlanguage", "about": "about",
    "multitasking": "multitasking", "clipboard": "clipboard", "game mode": "gaming-gamemode",
}
SITES = {
    "youtube": ("https://www.youtube.com", "https://www.youtube.com/results?search_query={}"),
    "google": ("https://www.google.com", "https://www.google.com/search?q={}"),
    "maps": ("https://www.google.com/maps", "https://www.google.com/maps/search/{}"),
    "gmail": ("https://mail.google.com", "https://mail.google.com/mail/u/0/#search/{}"),
    "amazon": ("https://www.amazon.ca", "https://www.amazon.ca/s?k={}"),
    "wikipedia": ("https://en.wikipedia.org", "https://en.wikipedia.org/w/index.php?search={}"),
    "reddit": ("https://www.reddit.com", "https://www.reddit.com/search/?q={}"),
    "netflix": ("https://www.netflix.com", "https://www.netflix.com/search?q={}"),
    "github": ("https://github.com", "https://github.com/search?q={}"),
    "chatgpt": ("https://chatgpt.com", None),
    "claude": ("https://claude.ai", None),
    "outlook": ("https://outlook.live.com", None),
    "icloud": ("https://www.icloud.com", None),
    "spotify": ("https://open.spotify.com", "https://open.spotify.com/search/{}"),
}
FOLDERS = {"downloads": "Downloads", "documents": "Documents", "desktop": "Desktop", "pictures": "Pictures",
           "music": "Music", "videos": "Videos", "home": ""}


def log_tier(tier, what):
    """One line per PC action in jarvis.log, so it's clear how often the cheap tiers do the job."""
    print(f"[pc] tier {tier}: {what}")


def _open(target):
    if IS_WINDOWS:
        os.startfile(target)
    else:
        webbrowser.open(target)


def open_settings(a):
    page = " ".join(str(a.get("page", "")).lower().split())
    uri = SETTINGS.get(page)
    if uri is None:
        hits = [k for k in SETTINGS if page and (page in k or k in page)]
        uri = SETTINGS[hits[0]] if hits else None
    if uri is None:
        return f"No settings page called {page}. Known: {', '.join(sorted(set(SETTINGS)))}."
    if not IS_WINDOWS:
        return "Settings pages only open on Windows."
    _open(f"ms-settings:{uri}")
    log_tier(1, f"settings {uri}")
    return f"Opened {page} settings."


def _set_dark_mode(on):
    import winreg
    path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 0 if on else 1)
    # Tell open windows the theme changed, so it applies now rather than at the next sign-in.
    import ctypes
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x2
    ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "ImmersiveColorSet",
                                             SMTO_ABORTIFHUNG, 2000, None)


def dark_mode(a):
    if not IS_WINDOWS:
        return "Dark mode switching only works on Windows."
    on = bool(a.get("on", True))
    try:
        _set_dark_mode(on)
    except OSError as e:
        return f"Couldn't change the theme: {e}"
    log_tier(1, f"dark mode {'on' if on else 'off'}")
    return f"Dark mode {'on' if on else 'off'}."


def open_website(a):
    raw = " ".join(str(a.get("site", "")).split())
    site = raw.lower()
    query = (a.get("search") or "").strip()
    browser = str(a.get("browser") or "")
    if browser_key(site):        # "open Brave" / "search cats on Brave" with the browser as the site
        browser, raw, site = site, "", ""
        if not query:
            exe = browser_path(browser_key(browser))
            if not exe:
                return f"I couldn't find {browser.title()} installed."
            subprocess.Popen([exe])
            return f"Opened {browser_key(browser).title()}."
    url = None
    if site in SITES:
        home, search = SITES[site]
        url = search.format(urllib.parse.quote_plus(query)) if query and search else home
    elif site.startswith(("http://", "https://")):
        url = raw
    elif site and "." in site and " " not in site:
        url = "https://" + raw
    elif query or site:
        url = SITES["google"][1].format(urllib.parse.quote_plus(" ".join(x for x in (raw, query) if x)))
    if not url:
        return "Which website, or what should I search for?"
    if browser and not browser_path(browser_key(browser)):
        return f"I couldn't find {browser.title()} installed, so nothing opened."
    used = open_url(url, browser)
    log_tier(1, f"open {url}" + (f" in {used}" if used else ""))
    return f"Opened {url}" + (f" in {used}." if used else ".")


def open_folder(a):
    name = str(a.get("folder", "")).lower().strip()
    if name not in FOLDERS:
        return f"I can open: {', '.join(FOLDERS)}."
    path = os.path.join(os.path.expanduser("~"), FOLDERS[name])
    if not os.path.isdir(path):
        return f"There's no {name} folder."
    if IS_WINDOWS:
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log_tier(1, f"folder {path}")
    return f"Opened {name}."


def set_brightness(a):
    if not IS_WINDOWS:
        return "Brightness control only works on Windows here."
    level = max(0, min(100, int(a.get("level", 50))))
    cmd = ("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
           f".WmiSetBrightness(1,{level})")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        return "This screen doesn't let Windows set its brightness (usual for desktop monitors)."
    log_tier(1, f"brightness {level}")
    return f"Brightness {level}%."


SKILLS = [
    {
        "name": "open_settings",
        "description": "Open a Windows Settings page directly, e.g. bluetooth, wifi, display, sound, "
                       "notifications, windows update, default apps, wallpaper. Much faster and cheaper "
                       "than use_computer.",
        "parameters": {"type": "object", "properties": {"page": {"type": "string"}}, "required": ["page"]},
        "run": open_settings,
    },
    {
        "name": "dark_mode",
        "description": "Turn Windows dark mode on or off instantly.",
        "parameters": {"type": "object", "properties": {"on": {"type": "boolean"}}, "required": ["on"]},
        "run": dark_mode,
    },
    {
        "name": "open_website",
        "description": ("Open a website in the browser, optionally straight to a search: site 'youtube' + search "
                        "'lo-fi music', site 'amazon' + search 'usb c cable', site 'maps' + search 'coffee near "
                        "me', or any address like 'bbc.co.uk'. 'Pull it up on Brave': browser='brave'. Use this instead of use_computer whenever the "
                        f"task is just opening a page or searching. Known sites: {', '.join(SITES)}."),
        "parameters": {"type": "object", "properties": {
            "site": {"type": "string"}, "search": {"type": "string"},
            "browser": {"type": "string", "description": "only if he named one: brave, chrome, edge or firefox"}},
            "required": ["site"]},
        "run": open_website,
    },
    {
        "name": "open_folder",
        "description": f"Open one of his folders in File Explorer: {', '.join(FOLDERS)}.",
        "parameters": {"type": "object", "properties": {"folder": {"type": "string", "enum": list(FOLDERS)}},
                       "required": ["folder"]},
        "run": open_folder,
    },
    {
        "name": "set_brightness",
        "description": "Set the screen brightness 0-100 (laptop screens; most desktop monitors can't).",
        "parameters": {"type": "object", "properties": {"level": {"type": "integer"}}, "required": ["level"]},
        "run": set_brightness,
    },
]
