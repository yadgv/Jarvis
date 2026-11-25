"""All settings in one place. Change these when porting to the Raspberry Pi."""
import os

# --- Brain ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_MODEL = "claude-haiku-5-5"          # fast + cheap for voice
MAX_HISTORY_TURNS = 10                   # conversation memory (pairs)
SYSTEM_PROMPT = (
    "You are JARVIS, a witty, concise British AI assistant for Ziad. "
    "Replies are spoken aloud, so keep them short (1-3 sentences), "
    "no markdown, no lists, no emojis. Address him as 'sir' occasionally."
)

# --- Activation ---
# "enter" = press Enter to talk (easy testing)
# "wake"  = say "Hey Jarvis"
MODE = "wake"
WAKE_WORD_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5
WAKE_CONSECUTIVE_FRAMES = 2              # frames in a row above threshold (raise if it misfires)
WAKE_CHIME = True                        # beep when Jarvis starts listening
WAKE_DEBUG = False                       # print wake-word scores to help tuning
FOLLOWUP_SECONDS = 5                     # after a reply, listen this long without the wake word (0 = off)

# --- Audio ---
SAMPLE_RATE = 16000
MIC_DEVICE = None                        # None = default mic; set index on the Pi
SILENCE_THRESHOLD = 500                  # minimum speech loudness; raise if it never stops listening
SILENCE_SECONDS = 1.2                    # pause length that ends your sentence
MAX_RECORD_SECONDS = 15
LISTEN_TIMEOUT = 4                       # give up if you don't start talking within this many seconds
AUTO_CALIBRATE = True                    # measure room noise at startup
NOISE_MULTIPLIER = 3.0                   # speech must be this many times louder than room noise

# --- Speech-to-text ---
# Windows: "small.en" is fine. Pi 4/5: use "tiny.en" or "base.en".
WHISPER_MODEL = "base.en"
WHISPER_DEVICE = "cpu"                   # "cuda" if you have an NVIDIA GPU
WHISPER_COMPUTE = "int8"

# --- Text-to-speech ---
# Main voice: Fish Audio (fish.audio -> API Keys)
FISH_API_KEY = os.getenv("FISH_API_KEY", "sk-fish-ynKspRFZMWh1irg4OTYwmm56XBqiouacct7WuzzNwTs")
FISH_VOICE_ID = "e13fa398a7f445a685316a3de6089ce7"
FISH_MODEL = "s2.1-pro-free"             # free tier

# Fallback voice: Piper voice files (.onnx + .onnx.json) go in ./voices
PIPER_VOICE = os.path.join(os.path.dirname(__file__), "voices", "en_GB-alan-medium.onnx")
