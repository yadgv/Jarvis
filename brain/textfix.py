"""Clean up text before it's drawn or spoken.

Models write curly quotes, odd spaces (5 V with a thin space), Ω and °, and
markdown. Worse, a reply read with the wrong encoding turns "servo's" into
"servoâs" and "220Ω" into "220Î©", which the whiteboard draws as junk and
the voice reads out letter by letter. fix() repairs and normalizes;
for_speech() also turns symbols into words."""
import re

# Runs of characters that are really UTF-8 bytes read as Latin-1/cp1252.
_CP1252 = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ"
_MOJIBAKE = re.compile(f"[Â-ô][\u0080-¿{_CP1252}]{{1,3}}")

_SAME = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "​": "", "‌": "", "‍": "", "﻿": "", "­": "",
    "–": "-", "—": " - ", "−": "-", "…": "...",
    "→": "->", "⟶": "->", "←": "<-", "↔": "<->", "⇒": "=>",
    "•": "-", "·": "-",
}


def _unmangle(m):
    s = m.group(0)
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return s


def fix(text) -> str:
    """Repair mis-decoded text and swap fancy punctuation for plain."""
    text = _MOJIBAKE.sub(_unmangle, str(text or ""))
    text = re.sub(r"[\u0080-\u009f]", "", text)  # stray control bytes
    for a, b in _SAME.items():
        text = text.replace(a, b)
    return text


_WORDS = [
    (re.compile(r"(\d)\s*k\s*Ω"), r"\1 kilo-ohm"), (re.compile(r"(\d)\s*[ΩΩ]"), r"\1 ohm"),
    (re.compile(r"[ΩΩ]"), " ohms"), (re.compile(r"°\s*C\b"), " degrees Celsius"),
    (re.compile(r"°\s*F\b"), " degrees Fahrenheit"), (re.compile(r"°"), " degrees"),
    (re.compile(r"µ|μ"), "micro"), (re.compile(r"±"), " plus or minus "),
    (re.compile(r"×"), " times "), (re.compile(r"≈"), " about "), (re.compile(r"≤"), " at most "),
    (re.compile(r"≥"), " at least "), (re.compile(r"<->"), " to and from "), (re.compile(r"->|=>"), " to "),
    (re.compile(r"<-"), " from "), (re.compile(r"\be\.g\.,?", re.I), "for example"),
    (re.compile(r"\bi\.e\.,?", re.I), "that is"), (re.compile(r"(\d)\s*V\b"), r"\1 volts"),
    (re.compile(r"(\d)\s*mA\b"), r"\1 milliamps"),
]
_MARKDOWN = re.compile(r"\*\*|__|`+|^#+\s*|^\s*[-*]\s+|\[(?P<link>[^\]]+)\]\([^)]*\)", re.M)
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿️‍]")


def for_speech(text) -> str:
    """fix(), plus symbols as words and no markdown or emoji, for the voice."""
    text = fix(text)
    text = _MARKDOWN.sub(lambda m: m.group("link") or "", text)
    text = _EMOJI.sub("", text)
    for pattern, words in _WORDS:
        text = pattern.sub(words, text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()
