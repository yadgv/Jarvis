"""Talk to Jarvis from your phone through a private Telegram bot.

Setup (once):
  1. In Telegram, message @BotFather, send /newbot, pick a name, and copy the token.
  2. Add to .env:   TELEGRAM_BOT_TOKEN=123456:ABC...
  3. Start Jarvis and message your bot. It answers with your Telegram user ID;
     add it to .env as TELEGRAM_ALLOWED_IDS=123456789 and restart Jarvis.
Only the IDs in TELEGRAM_ALLOWED_IDS get answers; everyone else is ignored.
Text and voice notes both work (voice notes are transcribed on the PC).
Jarvis must be running on the PC for the bot to answer.
"""
import os
import tempfile
import threading
import time

import requests

import config

API = "https://api.telegram.org"
PHONE_NOTE = ("[Sent from his phone by Telegram: he may not be at the PC. Your reply is shown as text, "
              "so it can be a little longer and may use short lists; no markdown symbols.]\n")
# Can't be undone from a phone: switching Jarvis off would leave nothing to answer.
PHONE_EXCLUDE = ("shut_down",)
_session = requests.Session()


def _token():
    return getattr(config, "TELEGRAM_BOT_TOKEN", None)


def _allowed():
    ids = getattr(config, "TELEGRAM_ALLOWED_IDS", "") or ""
    return {int(x) for x in str(ids).replace(",", " ").split() if x.strip().lstrip("-").isdigit()}


def _call(method, timeout=15, **params):
    r = _session.post(f"{API}/bot{_token()}/{method}", json=params, timeout=timeout)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description', r.status_code)}")
    return data["result"]


def send(chat_id, text):
    for i in range(0, max(1, len(text)), 4000):  # Telegram's limit is 4096 per message
        _call("sendMessage", chat_id=chat_id, text=text[i:i + 4000] or "…")


def notify(text) -> bool:
    """Send a message to every allowed Telegram user (e.g. a long brief that's
    too much to read aloud). False if the bot isn't set up."""
    ids = _allowed()
    if not _token() or not ids:
        return False
    for chat_id in ids:
        send(chat_id, text)
    return True


def _voice_to_text(file_id):
    path = _call("getFile", file_id=file_id)["file_path"]
    r = _session.get(f"{API}/file/bot{_token()}/{path}", timeout=30)
    r.raise_for_status()
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(path)[1] or ".ogg")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(r.content)
        from audio.stt import transcribe  # faster-whisper reads .ogg/.oga directly
        return transcribe(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _think(text):
    from brain import llm
    return " ".join(llm.think_stream(text, note=PHONE_NOTE, exclude_tools=PHONE_EXCLUDE)).strip()


def handle(update):
    """Answer one Telegram update. Returns the reply sent (or None)."""
    msg = update.get("message") or {}
    chat, sender = msg.get("chat", {}).get("id"), msg.get("from", {}).get("id")
    if chat is None or sender is None:
        return None
    allowed = _allowed()
    if sender not in allowed:
        if not allowed and msg.get("chat", {}).get("type") == "private":
            reply = (f"Hello. Your Telegram ID is {sender}. To let me answer you, add "
                     f"TELEGRAM_ALLOWED_IDS={sender} to the .env file on the PC and restart Jarvis.")
            send(chat, reply)
            print(f"[telegram] message from {sender}, who isn't allowed yet (their ID was sent back)")
            return reply
        print(f"[telegram] ignored a message from {sender} (not in TELEGRAM_ALLOWED_IDS)")
        return None
    text = (msg.get("text") or "").strip()
    voice = msg.get("voice") or msg.get("audio")
    try:
        _call("sendChatAction", chat_id=chat, action="typing")
    except Exception:
        pass
    if not text and voice:
        try:
            text = _voice_to_text(voice["file_id"])
        except Exception as e:
            print(f"[telegram] voice note failed: {e}")
            send(chat, "Sorry, I couldn't make out that voice note.")
            return None
        if not text:
            send(chat, "I couldn't hear any words in that voice note.")
            return None
    if not text:
        return None
    if text.startswith("/start"):
        reply = "Jarvis here. Send me a message or a voice note."
        send(chat, reply)
        return reply
    print(f"You (phone): {text}")
    import ui_events
    ui_events.emit("you", f"(phone) {text}")
    try:
        reply = _think(text) or "Done."
    except Exception as e:
        print(f"[telegram] brain error: {e}")
        reply = "I'm having trouble reaching my servers, sir."
    print(f"JARVIS (phone): {reply}")
    send(chat, reply)
    return reply


def _loop():
    offset = None
    failures = 0
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            updates = _call("getUpdates", timeout=40, **params)
            failures = 0
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    handle(u)
                except Exception as e:
                    print(f"[telegram] couldn't answer a message: {e}")
        except Exception as e:
            failures += 1
            if failures in (1, 10) or failures % 100 == 0:
                print(f"[telegram] connection problem ({e}); retrying")
            time.sleep(min(60, 2 * failures))


def start():
    """Run the bot in the background if a token is set."""
    if not _token():
        return False
    if not _allowed():
        print("[telegram] bot on, but TELEGRAM_ALLOWED_IDS is empty: message the bot to get your ID")
    threading.Thread(target=_loop, daemon=True, name="telegram").start()
    print("[telegram] phone bot running")
    return True
