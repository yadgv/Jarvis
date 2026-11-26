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
