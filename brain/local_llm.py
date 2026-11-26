"""Optional: answer easy questions with a free model running on this PC (Ollama).

Idea from OpenJarvis (github.com/open-jarvis/OpenJarvis, Apache-2.0), which
routes each query to a local or cloud model by how hard it looks. The scoring
below is cut down from its learning/routing/complexity.py for spoken questions.

Easy = short, needs no tool (weather, timers, music, email, the screen...),
and no deep reasoning, e.g. "how many ounces in a pound" or "tell me a joke".
Everything else, and anything the local model isn't sure about, goes to Claude
as before. Off unless LOCAL_MODEL is set in config.py.

Setup (Windows):
  1. Install Ollama from ollama.com/download (it runs in the background).
  2. In a terminal: ollama pull llama3.2:3b     (about 2 GB)
  3. In config.py: LOCAL_MODEL = "llama3.2:3b"
"""
import re
import time

import config

URL = getattr(config, "LOCAL_MODEL_URL", "http://localhost:11434/v1/chat/completions")
MAX_WORDS = 18          # longer requests go to Claude
RETRY_MINUTES = 5       # after Ollama fails to answer, leave it alone this long
HANDOFF = "[claude]"

# From OpenJarvis's complexity signals (math / reasoning / multi-step / creative).
_HARD = re.compile(
    r"\bsolve\b|\bintegral\b|\bequation\b|\bproof\b|\bderivative\b|\bprobability\b|"
    r"\bexplain\b|\banalyze\b|\bcompare\b|\bwhy\b|\bstep[- ]by[- ]step\b|\bpros\s+and\s+cons\b|"
    r"\btrade-?\s*offs?\b|\bevaluate\b|\band\s+also\b|\bthen\b|\bdraft\b|\bwrite\b|\bdesign\b|\bplan\b",
    re.IGNORECASE)

# Things only Claude can do here, because they use one of Jarvis's tools or
# need fresh information.
_NEEDS_TOOL = re.compile(
    r"\b(weather|temperature|rain|snow|forecast|time|today|tonight|tomorrow|yesterday|date|"
    r"timer|alarm|remind|reminder|schedule|calendar|meeting|event|email|emails|mail|inbox|"
    r"reply|send|text|message|telegram|phone|call|play|pause|skip|music|song|volume|"
    r"open|close|click|type|screen|window|app|computer|pc|shut|restart|lights?|light|"
    r"remember|forget|note|news|latest|current|price|score|game|stock|search|look\s+up|"
    r"google|find|buzz|claude|code|job|watch|check|turn|set|start|stop|cancel|my|mine|"
    r"whiteboard|board|diagram|drawing|draw|show|clear|erase|wipe|hide|step|next|back|wire|wiring)\b",
    re.IGNORECASE)

SYSTEM = (
    "You are Jarvis, a witty British butler AI, answering out loud in one or two short "
    "sentences, with no lists or markdown. You have no tools and no internet. If the "
    "question needs current information, his personal data, an action on his computer, "
    f"or you are not sure of the answer, reply with exactly {HANDOFF} and nothing else."
)

_off_until = 0.0


def enabled() -> bool:
    return bool(getattr(config, "LOCAL_MODEL", "")) and time.monotonic() >= _off_until


def is_easy(text: str) -> bool:
    text = (text or "").strip()
    words = text.split()
    return (0 < len(words) <= MAX_WORDS and not _HARD.search(text)
            and not _NEEDS_TOOL.search(text))


def should_use(text: str, followup=False, note="") -> bool:
    return enabled() and not followup and not note and is_easy(text)


def failed(e: Exception):
    """Ollama isn't running or broke: use Claude for a while."""
    global _off_until
    _off_until = time.monotonic() + RETRY_MINUTES * 60
    print(f"[brain] local model failed ({type(e).__name__}: {str(e)[:120]}); "
          f"using Claude for {RETRY_MINUTES} minutes")


def target() -> dict:
    return {"url": URL, "model": config.LOCAL_MODEL}


def handed_off(text: str) -> bool:
    t = text.strip().lower()
    return not t or t.startswith(HANDOFF[:-1]) or "[claude" in t
