"""Reaching him on his phone when he's away from the PC.

- A background job finishes (or fails) while he's away: a Telegram message.
- A job reaches a risky step ("CONFIRM: send the email?") while he's away: a
  Telegram message with Approve / Deny buttons; the job waits for his tap.
  Optionally his phone also rings first (CallMeBot's free Telegram call, if
  CALLMEBOT_USER is set), so he doesn't miss it.
Needs the Telegram bot set up (telegram_bot.py).
"""
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


SKILLS = [
    {
        "name": "test_phone_alerts",
        "description": ("Send a test phone alert now: an Approve/Deny message on Telegram, plus a phone call "
                        "if calls are set up. Use for 'test my phone alerts', 'test the call', 'call my phone', "
                        "'test Telegram approvals'."),
        "parameters": {"type": "object", "properties": {}},
        "run": test_phone,
    },
]
