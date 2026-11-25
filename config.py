"""All settings in one place. Change these when porting to the Raspberry Pi."""
import os
import platform


def _load_env_file():
    """Read KEY=value lines from a .env file next to this one, so API keys
    work no matter which terminal or editor starts Jarvis. Real environment
    variables win. The .env file is git-ignored."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

ON_PI = platform.machine().lower() in ("aarch64", "armv7l", "arm64") and platform.system() == "Linux"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis.log")  # None to turn off

# --- Brain ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("[setup] ANTHROPIC_API_KEY is not set, so Jarvis can't think.\n"
          "        Put this line in a file called .env in the jarvis folder:\n"
          "        ANTHROPIC_API_KEY=sk-ant-...")
LLM_MODEL = "claude-haiku-5-5"          # fast + cheap for voice
MAX_HISTORY_TURNS = 10                   # conversation memory (pairs)
MEMORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory")
HISTORY_MAX_AGE_HOURS = 6                # pick up the last conversation if it's newer than this
MAX_FACTS = 100                          # long-term facts kept in memory/facts.json
SYSTEM_PROMPT = (
    "You are JARVIS, a witty, concise British AI assistant for Ziad. "
    "Replies are spoken aloud, so keep them short (1-3 sentences), "
    "no markdown, no lists, no emojis. Address him as 'sir' occasionally. "
    "When he tells you something worth knowing later, or asks you to remember "
    "something, save it with the remember tool. Use your tools for timers, "
    "alarms, weather, his calendar, share prices, opening apps, volume and music, and anything "
    "current you'd need to look up. "
    "If he wants you to turn off, use the shut_down tool."
)

# --- Skills ---
HOME_CITY = "Courtice, Ontario"          # "Place, Region/Country"; used when you ask for the weather without a city
HOME_COORDS = (43.91, -78.79)            # lat, lon of HOME_CITY; skips the lookup (None to look it up)
TEMPERATURE_UNIT = "celsius"             # or "fahrenheit"
# Private iCal links of your calendars (read-only), space-separated. webcal:// links work too.
# Set CALENDAR_ICS_URLS in .env to override. iCloud: Calendar app > share calendar > Public Calendar.
# Google Calendar: Settings > your calendar > Integrate calendar > Secret address in iCal format.
CALENDAR_ICS_URLS = os.getenv(
    "CALENDAR_ICS_URLS",
    "webcal://p176-caldav.icloud.com/published/2/MTcxOTk5NzcwMDgxNzE5OaZmraEpYkLTlOLxNgWQzDEesl3gCEFrjfHZ6SWrN8Rf",
).split()
# Apps Jarvis can open by name. Anything in the Windows Start menu works too
# ("open Spotify"), so only add ones it can't find. Values are run as-is.
APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    # Store apps have no Start-menu shortcut file, so they're opened by their app id
    "apple music": r"shell:AppsFolder\AppleInc.AppleMusicWin_nzyj5cx40ttqa!App",
    "music": r"shell:AppsFolder\AppleInc.AppleMusicWin_nzyj5cx40ttqa!App",
}

# --- Activation ---
# "enter" = press Enter to talk (easy testing)
# "wake"  = say "Hey Jarvis"
MODE = "wake"
WAKE_WORD_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5
WAKE_CONSECUTIVE_FRAMES = 2              # frames in a row above threshold (raise if it misfires)
WAKE_CHIME = True                        # beep when Jarvis starts listening
WAKE_DEBUG = False                       # print wake-word scores to help tuning
BARGE_IN = True                          # say "Hey Jarvis" while he's talking to cut him off
BARGE_IN_THRESHOLD = 0.6                 # stricter than WAKE_THRESHOLD (the mic hears his voice too)
FOLLOWUP_SECONDS = 5                     # after a reply, listen this long without the wake word (0 = off)

# --- Audio ---
SAMPLE_RATE = 16000
MIC_DEVICE = None                        # None = default mic; set index on the Pi
VAD_AGGRESSIVENESS = 2                   # voice detector strictness 0-3 (raise if noise counts as speech)
MIN_SPEECH_LEVEL = 60                    # quietest speech that counts (used with the voice detector)
SILENCE_THRESHOLD = 500                  # loudness-only fallback if the voice detector isn't installed
SILENCE_SECONDS = 0.8                    # pause that ends your sentence (raise if it cuts you off)
MAX_RECORD_SECONDS = 15
LISTEN_TIMEOUT = 4                       # give up if you don't start talking within this many seconds
AUTO_CALIBRATE = True                    # measure room noise at startup
NOISE_MULTIPLIER = 3.0                   # speech must be this many times louder than room noise

# --- Speech-to-text ---
# Windows: "small.en" is fine. Pi 4/5: use "tiny.en" or "base.en".
WHISPER_MODEL = "tiny.en" if ON_PI else "base.en"
WHISPER_DEVICE = "cpu"                   # "cuda" if you have an NVIDIA GPU
WHISPER_COMPUTE = "int8"

# --- Text-to-speech ---
# Main voice: Fish Audio (fish.audio -> API Keys)
FISH_API_KEY = os.getenv("FISH_API_KEY", "sk-fish-ynKspRFZMWh1irg4OTYwmm56XBqiouacct7WuzzNwTs")
FISH_VOICE_ID = "e13fa398a7f445a685316a3de6089ce7"
FISH_MODEL = "s2.1-pro-free"             # free tier

# Fallback voice: Piper voice files (.onnx + .onnx.json) go in ./voices
PIPER_VOICE = os.path.join(os.path.dirname(__file__), "voices", "en_GB-alan-medium.onnx")
