"""Ask before using the paid AI (Claude).

Groq's free models do almost everything. When only Claude can do something
(the free ones failed, or it needs to see the screen), Jarvis asks first:
"The free models couldn't manage that, sir. Shall I use Claude? It costs a
little." A yes covers that one request (a whole screen task counts as one,
however many steps it takes); "yes, always" turns the question off, and so
does unticking "Ask before using paid AI" in Settings.
"""
import re
import threading

QUESTION = "The free models couldn't manage that, sir. Shall I use Claude for it? It costs a little."
TOOL_NOTE = ("needs Claude, the paid AI, and he hasn't said yes yet. Ask him in one short sentence whether to "
             "use Claude for it (it costs a little). Only if he says yes, call this tool again.")

_lock = threading.Lock()
_asked = None        # {"request": what he asked, or None when a tool asked} while waiting for his answer
_granted = False     # yes for the request being worked on now
_straight = False    # ...and it's one the free models already failed at: go straight to Claude
_local = threading.local()   # background tasks carry the yes they started with

_YES = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|go for it|please do|use (it|claude)|fine|"
                  r"of course|alright|all right|affirmative|why not)\b")
_NO = re.compile(r"\b(no|nope|nah|don't|do not|never mind|nevermind|cancel|skip|forget it|not now)\b")
_ALWAYS = re.compile(r"\b(always|every time|don't ask|stop asking|from now on|whenever)\b")


class PaidNeeded(RuntimeError):
    """Raised instead of calling Claude when he hasn't said yes."""

    def __init__(self, what="This"):
        super().__init__(f"{what} {TOOL_NOTE}")


def ask_first() -> bool:
    try:
        from brain import settings
        return bool(settings.app().get("ask_paid", True))
    except Exception:
        return True


def allowed() -> bool:
    """May Claude be used right now?"""
    if not ask_first():
        return True
    override = getattr(_local, "ok", None)
    if override is not None:
        return override
    return _granted


def asked(request=None):
    """He's being asked now; request is the words to answer again if he says yes."""
    global _asked
    with _lock:
        _asked = {"request": request}


def waiting() -> bool:
    return _asked is not None


def answer(text: str):
    """Called at the start of each turn with what he said. Returns the request
    to work on: his words, or (after a yes to a question about a reply the free
    models couldn't give) the request he'd asked before."""
    global _asked, _granted, _straight
    with _lock:
        pending, _asked = _asked, None
        _granted = _straight = False
    if pending is None:
        return text
    said = re.sub(r"[^a-z' ]", " ", (text or "").lower())
    if _NO.search(said) and not _YES.search(said.replace("don't ask", "")):
        print("[paid] he said no to Claude")
        return text
    if not _YES.search(said) and not _ALWAYS.search(said):
        return text      # he moved on to something else
    if _ALWAYS.search(said):
        try:
            from brain import settings
            settings.save({"ask_paid": False})
            print("[paid] he said always: no more asking before Claude")
        except Exception as e:
            print(f"[paid] couldn't save 'always': {e}")
    with _lock:
        _granted = True
        _straight = bool(pending["request"])
    print("[paid] he said yes to Claude for this request")
    if pending["request"]:
        return f"[He said yes to using Claude. Answer his earlier request now:] {pending['request']}"
    return text


def straight_to_claude() -> bool:
    return _straight and allowed()


def carry():
    """The yes in force now, to hand to a background task's thread."""
    return allowed()


def set_for_thread(ok):
    _local.ok = ok


def reset():
    global _asked, _granted, _straight
    with _lock:
        _asked, _granted, _straight = None, False, False
    _local.ok = None
