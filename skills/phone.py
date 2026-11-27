"""Reaching him on his phone when he's away from the PC.

- A background job finishes (or fails) while he's away: a Telegram message.
- A job reaches a risky step ("CONFIRM: send the email?") while he's away: a
  Telegram message with Approve / Deny buttons; the job waits for his tap.
  Optionally his phone also rings first (CallMeBot's free Telegram call, if
  CALLMEBOT_USER is set), so he doesn't miss it.
Needs the Telegram bot set up (telegram_bot.py).
"""
import os
import re
import time
from urllib.parse import quote

import requests

import config
import ui_events

AWAY_AFTER = 180          # seconds without a word from him = he's away from the PC
CONFIRM_WAIT = 15 * 60    # how long a job waits for his tap


def away() -> bool:
    return time.time() - ui_events.last_you > float(getattr(config, "PHONE_AWAY_SECONDS", AWAY_AFTER))


def ready() -> bool:
    import telegram_bot
    return bool(getattr(config, "PHONE_ALERTS", True) and telegram_bot._token() and telegram_bot._allowed()
                and getattr(config, "TELEGRAM_ON", True))


def notify(text: str) -> bool:
    """A message on his phone if he's away and the bot is set up. True if sent."""
    if not (ready() and away()):
        return False
    try:
        import telegram_bot
        return telegram_bot.notify(text)
    except Exception as e:
        print(f"[phone] couldn't send: {e}")
        return False


def ring(text: str) -> bool:
    """Ring his Telegram (free CallMeBot call that reads text out). Only if he set CALLMEBOT_USER."""
    user = (getattr(config, "CALLMEBOT_USER", "") or "").strip()
    if not user:
        return False
    user = user if user.startswith("@") else "@" + user
    try:
        r = requests.get(f"https://api.callmebot.com/start.php?user={quote(user)}&text={quote(text[:250])}"
                         "&lang=en-GB-Standard-B&rpt=2", timeout=30)
        print(f"[phone] rang {user}: {r.status_code}")
        return r.ok
    except requests.RequestException as e:
        print(f"[phone] couldn't ring: {e}")
        return False


def confirm(question: str, wait: float = CONFIRM_WAIT):
    """Ask him on his phone (buttons). True = approved, False = denied, None = couldn't ask or no answer."""
    if not (ready() and away()):
        return None
    import telegram_bot
    ring(f"Jarvis here. I need your OK: {question}. Check Telegram.")
    print(f"[phone] asking on Telegram: {question}")
    answer = telegram_bot.ask(f"Jarvis needs your OK:\n{question}", wait=wait)
    print(f"[phone] answer: {answer}")
    return answer


def status() -> str:
    """One line for the log: is the phone set up?"""
    import telegram_bot
    bot = "set up" if (telegram_bot._token() and telegram_bot._allowed()) else \
        "NOT set up (TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_IDS in .env)"
    user = (getattr(config, "CALLMEBOT_USER", "") or "").strip()
    call = f"on for {user}" if user else "off (add CALLMEBOT_USER=@yourname to .env)"
    return f"[phone] Telegram bot {bot}; calls {call}; alerts {'on' if getattr(config, 'PHONE_ALERTS', True) else 'off'}"


def _test_run(wait: float):
    import telegram_bot
    rang = ring("Jarvis here. This is a test call. Check Telegram and tap Approve or Deny.")
    print(f"[phone] test: call {'placed' if rang else 'not placed'}; sending Approve/Deny to Telegram")
    answer = telegram_bot.ask("Test from Jarvis: tap Approve or Deny.", wait=wait)
    word = {True: "Approve", False: "Deny", None: "nothing (timed out)"}[answer]
    print(f"[phone] test answer: {word}")
    telegram_bot.notify(f"Test done: you tapped {word}. Phone alerts work." if answer is not None
                        else "Test timed out: no tap received.")
    ui_events.emit("info", f"Phone test: you tapped {word}.")


def test_phone(a=None):
    """Send a test Approve/Deny to Telegram (and ring if CALLMEBOT_USER is set), right now."""
    import threading
    import telegram_bot
    line = status()
    print(line)
    if not (telegram_bot._token() and telegram_bot._allowed()):
        return ("The Telegram bot isn't set up, so I can't test. He needs TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_ALLOWED_IDS in .env (see the README, 'Talk to Jarvis from your phone').")
    threading.Thread(target=_test_run, args=(120,), daemon=True, name="phone-test").start()
    calls = (getattr(config, "CALLMEBOT_USER", "") or "").strip()
    return ("Test sent: an Approve/Deny message is on its way to his Telegram"
            + (f", and his phone should ring (CallMeBot, {calls})." if calls else
               ". No call, because CALLMEBOT_USER isn't set in .env.")
            + " He has 2 minutes to tap; the result shows on Telegram and in the log.")


TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024    # a bot can send files up to 50 MB
_URL = re.compile(r"https?://\S+")


def _what(request: str, a: dict) -> str:
    """What he wants sent: link, file, deck, brief, screen or text."""
    kind = str(a.get("what") or "").lower().strip()
    if kind:
        return kind
    r = request.lower()
    if re.search(r"\b(?:link|url|address|website|page|site|tab)\b", r):
        return "link"
    if re.search(r"\b(?:slides?|deck|presentation|powerpoint|script|document|doc|essay|report)\b", r):
        return "deck"
    if re.search(r"\bbrief|summary|key points\b", r):
        return "brief"
    if re.search(r"\b(?:file|pdf|picture|photo|image)\b", r):
        return "file"
    return "text" if a.get("text") else "screen"


def _send_path(path: str, caption: str) -> str:
    import telegram_bot
    size = os.path.getsize(path)
    if size > TELEGRAM_FILE_LIMIT:
        return f"{os.path.basename(path)} is {size // (1024 * 1024)} MB, too big for Telegram (50 MB). Say so."
    telegram_bot.send_file(path, caption)
    print(f"[phone] sent the file {path} to Telegram")
    return f"Sent {os.path.basename(path)} to his phone (Telegram)."


def send_to_phone(a=None):
    """ "Send this link to my phone", "send me the slides", "text me that": a Telegram message or file now."""
    import telegram_bot
    a = a or {}
    if not (telegram_bot._token() and telegram_bot._allowed()):
        return ("I can't send to his phone: the Telegram bot isn't set up (TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_ALLOWED_IDS in .env). Say so.")
    request = str(a.get("request") or "")
    text = str(a.get("text") or "").strip()
    kind = _what(request, a)
    try:
        if a.get("file"):
            from skills import files
            path, err = files._find_one(str(a["file"]))
            return _send_path(path, str(a.get("caption") or "")) if path else err
        if text and kind == "text":
            telegram_bot.notify(text)
            print(f"[phone] sent a message to Telegram: {text[:80]}")
            return "Sent it to his phone (Telegram)."
        if kind == "deck":
            from skills import documents
            doc, err = documents.find_doc(str(a.get("name") or ""))   # open in PowerPoint/Word, else the last made
            if doc and doc.get("path"):
                return _send_path(doc["path"], (doc.get("spec") or {}).get("title", ""))
            return err or "There's no deck or document of his to send yet. Ask which file."
        if kind == "brief":
            from skills import workspace
            if workspace._ws.get("file") and os.path.exists(workspace._ws["file"]):
                return _send_path(workspace._ws["file"], workspace._ws.get("title", ""))
            if workspace._ws.get("doc"):
                telegram_bot.notify(re.sub(r"<[^>]+>", "", workspace._ws["doc"])[:3900])
                return "Sent the brief to his phone (Telegram)."
            return "There's no brief to send. Offer to brief what's on his screen first."
        from skills import sight
        seen = sight.read()
        url = seen.get("url") or ""
        if not url:
            m = _URL.search(text or seen.get("text") or "")
            url = m.group(0) if m else ""
        if kind == "link" or (kind == "screen" and url):
            if not url:
                return "I couldn't see a web address on his screen. Ask him to open the page in his browser."
            telegram_bot.notify(f"{seen.get('title') or 'Link'}\n{url}")
            print(f"[phone] sent the link to Telegram: {url}")
            return f"Sent the link to his phone (Telegram): {seen.get('title') or url}."
        body = text or (seen.get("selection") or seen.get("text") or "").strip()
        if not body:
            return "There's nothing to send. Ask what he'd like on his phone."
        telegram_bot.notify(((seen.get("title") + "\n\n") if seen.get("title") and not text else "") + body[:3900])
        return "Sent it to his phone (Telegram)."
    except Exception as e:
        print(f"[phone] couldn't send to Telegram: {type(e).__name__}: {e}")
        return f"Sending to his phone failed ({type(e).__name__}: {str(e)[:120]}). Say so; don't say it was sent."


SKILLS = [
    {
        "name": "send_to_phone",
        "description": ("Send something to his phone now on Telegram: the link of the page he's on, a file, his "
                        "slides or document, the brief, or any text (a list, an address, a note). Use for 'send "
                        "this to my phone', 'text me the link', 'send me the slides', 'put that on my phone'. "
                        "Never say something was sent unless this tool said so."),
        "parameters": {"type": "object", "properties": {
            "what": {"type": "string", "enum": ["link", "text", "file", "deck", "brief", "screen"]},
            "text": {"type": "string", "description": "the words to send, when he wants a note or list"},
            "file": {"type": "string", "description": "a file name or path, when he names a file"}}},
        "run": send_to_phone,
    },
    {
        "name": "test_phone_alerts",
        "description": ("Send a test phone alert now: an Approve/Deny message on Telegram, plus a phone call "
                        "if calls are set up. Use for 'test my phone alerts', 'test the call', 'call my phone', "
                        "'test Telegram approvals'."),
        "parameters": {"type": "object", "properties": {}},
        "run": test_phone,
    },
]
