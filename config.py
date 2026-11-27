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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not (ANTHROPIC_API_KEY or GROQ_API_KEY or os.getenv("OPENROUTER_API_KEY") or os.getenv("CEREBRAS_API_KEY")
        or os.getenv("GEMINI_API_KEY") or os.getenv("MISTRAL_API_KEY") or os.getenv("GITHUB_MODELS_TOKEN")):
    print("[setup] No brain is set up, so Jarvis can't think.\n"
          "        Put this line in a file called .env in the jarvis folder (free key from console.groq.com):\n"
          "        GROQ_API_KEY=gsk_...")
# Which brain answers, cheapest first. A brain that fails (rate limit, no
# credit, down) is rested and the next one answers. Claude is paid, so it's
# last; screen control and looking at the screen always use Claude.
# Free brains first (each used only if its key is in .env), Claude last (it asks first).
BRAIN_ORDER = ["groq", "cerebras", "gemini", "mistral", "github", "openrouter", "claude"]
# More free model providers to fall back on when Groq's free limits run out. All optional:
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")        # cloud.cerebras.ai: very fast, about 1M free tokens a day
CEREBRAS_MODELS = ["gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507"]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")            # aistudio.google.com/apikey: good, and it can see pictures
GEMINI_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")          # console.mistral.ai (free "Experiment" plan)
MISTRAL_MODELS = ["mistral-medium-latest", "mistral-small-latest"]
GITHUB_MODELS_TOKEN = os.getenv("GITHUB_MODELS_TOKEN")  # github.com/settings/tokens: fine-grained, "Models: read"
GITHUB_MODELS = ["openai/gpt-4.1-mini"]
# Free picture understanding ("what's in this photo?") before Claude: tried in this order.
FREE_VISION = ["gemini", "github"]
# Browser for links and searches: "" = Windows' default browser; or "brave", "chrome", "edge", "firefox".
BROWSER = os.getenv("JARVIS_BROWSER", "")
# If Apple Music's own buttons can't play a song: False = play it on YouTube (free);
# True = let Claude click through Apple Music (paid, asks first).
MUSIC_SCREEN_CONTROL = False

# Groq's free models (console.groq.com, GROQ_API_KEY=gsk_... in .env). Each has
# its own free limits, so when one is busy the next takes over.
GROQ_MODELS = [
    "openai/gpt-oss-120b",                 # best tool use on Groq's free tier
    "qwen/qwen3.8-27b",                    # small free token limit: gets fewer tools and less history
    "openai/gpt-oss-20b",
]
# (llama-3.3-70b-versatile was shut down by Groq on 16 Aug 2026.)
# Models with small free per-minute token limits ("Request too large"): sent
# only the most relevant tools and the last couple of turns.
GROQ_LEAN_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
GROQ_SMALL_MODELS = ["openai/gpt-oss-20b"]  # tried first for small background jobs (saving facts)
# Drawing diagrams on the whiteboard ("show me how to wire a servo"): a big
# model writes the picture, so these are tried first (then the usual order).
WHITEBOARD_MODELS = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
GROQ_HISTORY_TURNS = 3                   # free models have small token limits: send the last few turns only
LLM_MODEL = "claude-haiku-5-5"          # Claude, when it's needed (fast + cheap for voice)
ASK_BEFORE_PAID = True                   # ask "Shall I use Claude?" before anything that costs money (also in Settings)
BACKGROUND_TASKS = True                  # long jobs (screen control, sorting files, 3D, documents) run while you talk to him
# Backup brain for when Claude credits run out: free models on OpenRouter
# (key from openrouter.ai/keys, put OPENROUTER_API_KEY=sk-or-... in .env).
# Tried in order; "openrouter/free" picks any free model that supports tools.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODELS = [
    "nvidia/nemotron-3.5-super-vl:free",   # fastest free model with good tool use
    "cohere/north-mini-code:free",         # backup choice
]
# ("openrouter/free" picked whatever model was up, some took 30s+ and read tool output aloud.)
# Optional free local model for easy questions (no tools needed), so they
# cost nothing and work offline. Off when empty. To turn on: install Ollama
# (ollama.com/download), run `ollama pull llama3.2:3b`, then set it here.
# Anything harder, or anything it isn't sure of, still goes to Claude.
LOCAL_MODEL = ""                         # e.g. "llama3.2:3b" (or "qwen2.5:3b")
# With no internet, simple commands (time, timers, alarms, reminders, volume,
# media keys, opening apps) work with no model at all; anything else goes to
# this Ollama model with only the offline tools. Uses LOCAL_MODEL if that's set.
# Setup: install Ollama (ollama.com/download), then `ollama pull llama3.2:3b`.
OFFLINE_MODEL = "llama3.2:3b"
OFFLINE_MODE = False                     # True = act as if the internet is down (for testing)
BACKUP_MINUTES = 15                      # after Claude fails, use the backup this long before retrying Claude
MAX_HISTORY_TURNS = 10                   # conversation memory (pairs)
# Folders (in your user folder) Jarvis may read, make files in and tidy up
# (skills/files.py). OneDrive copies count too. Add more names or full paths.
FILE_FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]

MEMORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory")
HISTORY_MAX_AGE_HOURS = 6                # pick up the last conversation if it's newer than this
MAX_FACTS = 100                          # long-term facts kept in memory/facts.json
AUTO_MEMORY = True                       # after each chat, save lasting facts he mentioned without being asked
FACTS_IN_PROMPT = 25                     # past this many saved facts, only the most relevant ones go to Claude
SYSTEM_PROMPT = (
    "You are JARVIS, a British AI assistant for Ziad. "
    "Replies are spoken aloud, so no markdown, no lists, no emojis, and never code: if he wants code or a "
    "file, make it with a tool and just say what you made. Never think out loud or talk about your tools. "
    "When he tells you something worth knowing later, or asks you to remember "
    "something, save it with the remember tool. Use your tools for timers, "
    "alarms, weather, his calendar, share prices, opening apps, volume and music, looking at and using his screen, and anything "
    "current you'd need to look up. "
    "If he wants you to turn off, use the shut_down tool. "
    "Never make up what an article, page, document or screen says: only summarize or brief text a tool "
    "actually read this turn. If you couldn't read it, say so plainly; never invent facts or figures."
)

# Personality and voice. These are the defaults; he can change them by voice
# ("be more casual", "talk faster", "call me Ziad"), saved in memory/settings.json.
STYLE = "butler"                         # butler, casual, brief, formal, playful
REPLY_LENGTH = "normal"                  # short, normal, long
CALL_ME = "sir"                          # how Jarvis addresses you; "nothing" for no title
VOICE_SPEED = 1.0                        # 0.7 (slower) to 1.5 (faster)
VOICE = "jarvis"                         # a name from VOICES below
# Fish Audio voices by name: copy a voice's ID from its page on fish.audio to add one.
VOICES = {
    "jarvis": "e13fa398a7f445a685316a3de6089ce7",
}

# --- Skills ---
# Arduino over USB (flash hardware/arduino/jarvis_bridge first). Port is found
# automatically; set it if not, e.g. "COM5" on Windows or "/dev/ttyACM0" on the Pi.
ARDUINO_PORT = None
ARDUINO_BAUD = 115200
ARDUINO_DEVICES = {                      # things to switch: name -> pin
    "built-in light": 13,
}
ARDUINO_SENSORS = {}                     # things to read: name -> pin, e.g. {"light sensor": "A0"}

# Looking at the screen uses a bigger model than the chat (better at reading screens).
SCREEN_MODEL = "claude-opus-5-5"
SCREEN_EFFORT = "low"                    # low = quickest answer; raise to medium for harder screens
# Clicking and typing for you (emergency stop: move the mouse into a screen corner).
COMPUTER_EFFORT = "medium"
COMPUTER_MAX_STEPS = 40                  # rounds of look-and-act before pausing to ask whether to keep going
# Morning briefing (weather, calendar, reminders, news) on your first hello of the day.
MORNING_BRIEFING = True
BRIEFING_FROM_HOUR = 4                   # a hello before this hour counts as the night before
BRIEFING_HEADLINES = 3
NEWS_REGION = ("en-CA", "CA", "CA:en")   # Google News language, country, edition
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
# Adding events to iCloud needs a sign-in with an app-specific password
# (appleid.apple.com > Sign-In and Security > App-Specific Passwords). Put in .env:
# ICLOUD_USERNAME=you@icloud.com and ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
ICLOUD_USERNAME = os.getenv("ICLOUD_USERNAME")
ICLOUD_APP_PASSWORD = os.getenv("ICLOUD_APP_PASSWORD")
ICLOUD_CALENDAR = os.getenv("ICLOUD_CALENDAR", "")   # calendar name to add to; empty = the first one
# Canvas (school courses): the school's Canvas address, e.g. learn.school.ca (or tell Jarvis
# "my Canvas is ..."). Sign-in happens once in a browser window: "sign in to Canvas". The
# calendar feed link (Canvas > Calendar > Calendar Feed) lets "what's due" work with no sign-in.
CANVAS_URL = os.getenv("CANVAS_URL", "")
CANVAS_CALENDAR_FEED = os.getenv("CANVAS_CALENDAR_FEED", "")
SCHOOL_FOLDER = os.getenv("SCHOOL_FOLDER", "")   # empty = Documents\School
# Reading Gmail (read-only): app password from myaccount.google.com/apppasswords. Put in .env:
# GMAIL_ADDRESS=you@gmail.com and GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
# Talk to Jarvis from your phone with a private Telegram bot (see telegram_bot.py):
# TELEGRAM_BOT_TOKEN from @BotFather; TELEGRAM_ALLOWED_IDS = your Telegram user ID(s).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_IDS = os.getenv("TELEGRAM_ALLOWED_IDS", "")
PHONE_ALERTS = True                      # away from the PC: finished jobs and Approve/Deny questions go to Telegram
PHONE_AWAY_SECONDS = 180                 # this long without talking to him = you're away
CALLMEBOT_USER = os.getenv("CALLMEBOT_USER", "")  # your Telegram @username: ring your phone for Approve/Deny (free, callmebot.com)
TELEGRAM_ON = True                       # the phone bot (also in the orb's right-click Settings)
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
# Playing songs by name: Jarvis opens this app and uses screen control to search and press play.
MUSIC_APP = "apple music"
MUSIC_OPEN_WAIT = 3                      # seconds to let the app open before searching
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

# Claude Code by voice: project name -> folder. Needs Claude Code installed and signed in.
CLAUDE_CODE_PROJECTS = {"jarvis": os.path.dirname(os.path.abspath(__file__))}
CLAUDE_CODE_PERMISSION_MODE = "acceptEdits"   # may edit files; asks (so skips) anything riskier
CLAUDE_CODE_TIMEOUT_MINUTES = 30

# The "Jarvis eyes" browser extension (browser_extension/, Load unpacked once) tells
# Jarvis what page you're on, its text and, when asked, its code. Must match background.js.
BROWSER_BRIDGE = True
BROWSER_BRIDGE_PORT = 47321

# Hold this key, talk, let go: your words are typed into the app you're in (None = off)
DICTATION_KEY = "f9"

# --- Activation ---
# "enter" = press Enter to talk (easy testing)
# "wake"  = say "Hey Jarvis"
MODE = "wake"
WAKE_WORD_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5
# Also wake on just "Jarvis": a short word said on its own (a pause before and
# after) is transcribed on the PC and wakes him only if it's his name.
WAKE_ON_NAME = True
NAME_MIN_SECONDS = 0.25                  # shorter sounds (clicks, coughs) are ignored
NAME_MAX_SECONDS = 1.2                   # longer than this is talking, not calling his name
NAME_PAUSE_SECONDS = 0.3                 # quiet needed before and after the word
WAKE_CONSECUTIVE_FRAMES = 2              # frames in a row above threshold (raise if it misfires)
WAKE_CHIME = True                        # beep when Jarvis starts listening
WAKE_DEBUG = False                       # print wake-word scores to help tuning
BARGE_IN = True                          # say "Hey Jarvis" while he's talking to cut him off
BARGE_IN_ON_NAME = True                  # just "Jarvis" (said on its own) cuts him off too
BARGE_IN_THRESHOLD = 0.6                 # stricter than WAKE_THRESHOLD (the mic hears his voice too)
FOLLOWUP_SECONDS = 12                    # conversation: after each reply, keep listening without the wake word
                                         # until he's quiet this long or says "thanks"/"that's all" (0 = off)
WAKE_VAD_THRESHOLD = 0.5                 # wake only if a voice detector also hears speech (0 = off; cuts TV/music wakes)
WAKE_NOISE_SUPPRESSION = ON_PI           # Speex noise suppression for the wake word (Linux only: pip install speexdsp-ns)
# Your-voice check for "Hey Jarvis", made by running: python train_my_voice.py
WAKE_VERIFIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory", "my_voice_verifier.pkl")
WAKE_VERIFIER_THRESHOLD = 0.3            # wake score above which your-voice check runs

# "Third person in the room": remember the last minute of talk before "Hey Jarvis"
# (in memory only, never saved) so "Jarvis, what do you think?" has context. Off by default.
ROOM_CONTEXT = False
ROOM_CONTEXT_SECONDS = 60

# --- Audio ---
SAMPLE_RATE = 16000
MIC_DEVICE = None                        # None = default mic; set index on the Pi
VAD_AGGRESSIVENESS = 2                   # voice detector strictness 0-3 (raise if noise counts as speech)
MIN_SPEECH_LEVEL = 60                    # quietest speech that counts (used with the voice detector)
SILENCE_THRESHOLD = 500                  # loudness-only fallback if the voice detector isn't installed
SILENCE_SECONDS = 0.6                    # pause that ends your sentence (raise if it cuts you off)
# Smart Turn (github.com/pipecat-ai/smart-turn) listens to *how* you stopped:
# a finished sentence ends after SMART_TURN_SILENCE, a mid-thought pause
# ("I want to... um") waits up to SMART_TURN_MAX_SILENCE. Off = SILENCE_SECONDS only.
SMART_TURN = True
SMART_TURN_SILENCE = 0.3
SMART_TURN_MAX_SILENCE = 2.0
SMART_TURN_MIN_SPEECH = 0.5                # seconds of speech before Smart Turn may end the turn
SMART_TURN_MODEL_URL = "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx"
SPEAKER_DROP = 0.35                      # sound quieter than this share of your voice is background (raise if chatter keeps him listening)
MAX_RECORD_SECONDS = 30
LISTEN_TIMEOUT = 6                       # give up if you don't start talking within this many seconds
AUTO_CALIBRATE = True                    # measure room noise at startup
NOISE_MULTIPLIER = 3.0                   # speech must be this many times louder than room noise

# Turn other apps down while Jarvis listens and talks (Windows; needs: pip install pycaw)
DUCK_APPS = ["AppleMusic.exe", "iTunes.exe", "Spotify.exe"]   # process names; [] = off
DUCK_VOLUME = 0.2                        # their volume while ducked (0-1 of what it was)

# --- Speech-to-text ---
# Bigger models hear more accurately but take longer. "small.en" (~250 MB, one-time
# download) mishears far less than "base.en" on a PC; Pi 4/5: "tiny.en" or "base.en".
WHISPER_MODEL = "tiny.en" if ON_PI else "small.en"
WHISPER_FALLBACK_MODEL = "base.en"       # used if the main one can't load (e.g. no internet for the download)
WHISPER_BEAM_SIZE = 1                    # readings tried (1 = fastest; 3 is a little more accurate but ~40% slower)
WHISPER_THREADS = min(8, os.cpu_count() or 4)   # CPU cores Whisper may use
# Words he uses that Whisper doesn't expect. They're given to Whisper as a hint,
# so "breadboard" isn't heard as "bare book". Add your own here, or say
# "Jarvis, learn the word ..." (saved in memory/vocab.json). Canvas class names are added too.
STT_WORDS = [
    "Jarvis", "breadboard", "Arduino", "resistor", "capacitor", "multimeter", "oscilloscope", "soldering",
    "thermodynamics", "photosynthesis", "mitochondria", "calculus", "derivative", "integral", "vector",
    "Canvas", "whiteboard", "Courtice", "Apple Music", "Python", "VS Code", "GitHub",
]
WHISPER_DEVICE = "cpu"                   # "cuda" if you have an NVIDIA GPU
WHISPER_COMPUTE = "int8"

# --- Text-to-speech ---
# Main voice: Fish Audio (fish.audio -> API Keys)
FISH_API_KEY = os.getenv("FISH_API_KEY", "sk-fish-ynKspRFZMWh1irg4OTYwmm56XBqiouacct7WuzzNwTs")
FISH_VOICE_ID = "e13fa398a7f445a685316a3de6089ce7"
FISH_MODEL = "s2.1-pro-free"             # free tier

# Fallback voice: Piper voice files (.onnx + .onnx.json) go in ./voices
PIPER_VOICE = os.path.join(os.path.dirname(__file__), "voices", "en_GB-alan-medium.onnx")
# Offline voice: used when Fish Audio is down or there's no internet. Pick one
# name from OFFLINE_VOICES (or say "use the fable voice offline"). Hear them all
# first with:  python try_voices.py     (or just one: python try_voices.py fable)
# Kokoro voices sound the most natural (needs pip install kokoro-onnx); Piper
# ones are lighter but more robotic. Each downloads into ./voices the first time.
OFFLINE_VOICE = "fable"
OFFLINE_VOICE_QUALITY = "best"           # Kokoro model: "best" (~310 MB, smoothest) or "small" (~90 MB)
OFFLINE_VOICES = {
    # Kokoro, British men (the Jarvis-like ones)
    "fable": "bm_fable",                 # warm, storyteller; the most natural British man
    "george": "bm_george",               # older, deeper, a bit formal
    "lewis": "bm_lewis",                 # deep, slower
    "daniel": "bm_daniel",               # lighter, plainer
    # Kokoro, the most natural overall (American)
    "michael": "am_michael",             # calm American man
    "fenrir": "am_fenrir",               # fuller American man
    "heart": "af_heart",                 # American woman, Kokoro's best-sounding voice
    "emma": "bf_emma",                   # British woman
    # Piper (lighter, more robotic)
    "alan": "en_GB-alan-medium",
    "northern": "en_GB-northern_english_male-medium",
}

# Jarvis's own pointer (pointer_overlay.py): a glowing arrow that shows you where things are on
# screen ("where's the export button?", "show me how to add page numbers"). Never moves your mouse.
POINTER = True
