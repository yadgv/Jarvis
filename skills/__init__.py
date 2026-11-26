"""Jarvis's skills (tools the language model can call).

Each skill module exposes SKILLS: a list of dicts with
    name, description, parameters (JSON Schema), run(args) -> str
That's provider-neutral: anthropic_tools() and openai_tools() turn it into the
format Claude or an OpenAI-style API (Groq, OpenAI, Ollama...) expects.
"""
import threading

# One module per line, so adding a skill doesn't clash with other changes.
from skills import arduino  # noqa: E402
from skills import briefing  # noqa: E402
from skills import buzz  # noqa: E402
from skills import calendar_events  # noqa: E402
from skills import claude_code  # noqa: E402
from skills import computer  # noqa: E402
from skills import edit_text  # noqa: E402
from skills import email_reader  # noqa: E402
from skills import icloud_calendar  # noqa: E402
from skills import jobs  # noqa: E402
from skills import memory_tools  # noqa: E402
from skills import music  # noqa: E402
from skills import news  # noqa: E402
from skills import pc_control  # noqa: E402
from skills import quick_actions  # noqa: E402
from skills import personality  # noqa: E402
from skills import reminders  # noqa: E402
from skills import screen  # noqa: E402
from skills import stocks  # noqa: E402
from skills import suggestions  # noqa: E402
from skills import system  # noqa: E402
from skills import timers  # noqa: E402
from skills import ui_automation  # noqa: E402
from skills import weather  # noqa: E402
from skills import whiteboard  # noqa: E402
from skills import files  # noqa: E402
from skills import documents  # noqa: E402
from skills import web_search  # noqa: E402

MODULES = [
    briefing,
    memory_tools,
    timers,
    reminders,
    jobs,
    suggestions,
    weather,
    news,
    web_search,
    buzz,
    calendar_events,
    email_reader,
    icloud_calendar,
    stocks,
    pc_control,
    quick_actions,
    ui_automation,
    music,
    screen,
    computer,
    claude_code,
    edit_text,
    system,
    arduino,
    whiteboard,
    files,
    documents,
    personality,
]
# Counts conversation turns, so a tool can tell "he said yes" (a later turn)
# from the model confirming its own draft in the same turn.
turn = 0


def new_turn():
    global turn
    turn += 1


SKILLS = [skill for module in MODULES for skill in module.SKILLS]
_BY_NAME = {s["name"]: s for s in SKILLS}


def register(new_skills):
    """Add tools found at runtime (e.g. from MCP servers). Names already taken are skipped."""
    for s in new_skills:
        if s["name"] not in _BY_NAME:
            SKILLS.append(s)
            _BY_NAME[s["name"]] = s


def anthropic_tools(exclude=()):
    return [
        {"name": s["name"], "description": s["description"], "input_schema": s["parameters"]}
        for s in SKILLS if s["name"] not in exclude
    ]


def _short(text, limit=160):
    """The first sentence of a description, for models with small token limits."""
    first = text.split(". ")[0].rstrip(".") + "."
    return first if len(first) <= limit else first[:limit - 1] + "…"


def openai_tools(exclude=(), short=False):
    return [
        {"type": "function",
         "function": {"name": s["name"], "description": _short(s["description"]) if short else s["description"],
                      "parameters": s["parameters"]}}
        for s in SKILLS if s["name"] not in exclude
    ]


# Tools every turn gets, even on a small model where only the relevant ones are sent.
CORE_TOOLS = ("remember", "forget", "set_timer", "get_weather", "web_search", "shut_down")
_STOP = set("a an the and or for of to in on at by with is are be it its his him he you your your's this that "
            "what when where how do does from into as can i me my please jarvis sir up out".split())


def _words(text):
    import re
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _STOP}


import re as _re
# Anything about drawing or the board goes to Jarvis's own whiteboard, never
# Paint or Microsoft Whiteboard through use_computer.
_BOARD = _re.compile(r"\b(white ?board|board|draw|drawing|drawn|diagram|sketch|visuali[sz]e|"
                     r"schematic|wiring|mind ?map|timeline|free[- ]body|forces? diagram|circuit|y ?=|plot|graph (?:of )?(?:y|f|sin|cos|tan|x)|step by step|wire (?:up|it|this|that|a|an|the)|show me how)\b", _re.I)
BOARD_TOOLS = ("show_diagram", "whiteboard_step")


_FILES = _re.compile(r"\b(files?|folders?|downloads|desktop|documents|pictures|organi[sz]e|tidy|sort (?:out )?my|"
                     r"clean (?:up )?my|rename|undo (?:that|it)|spreadsheet|\.(?:txt|csv|pdf|docx?|py|ino)\b|"
                     r"\b(?:make|create|write|save|start) (?:me |up )?(?:a |an |my )?[\w' -]{0,30}?\b(?:note|notes|list|document|doc|"
                     r"script|file|letter|essay|spreadsheet|table|program|sketch)\b|"
                     r"\b(?:find|where(?:'s| is| are)|locate|open) my\b|\bresume\b|\bcv\b)", _re.I)
_DOCS = _re.compile(r"\b(word doc(?:ument)?|docx|power ?point|slides?|slide deck|presentation|excel|spreadsheet|"
                    r"pdf|graph|chart|plot)\b", _re.I)
DOC_TOOLS = ("make_document", "show_chart")
FILE_TOOLS = ("make_file", "find_files", "read_file", "open_file", "organize_folder", "file_action", "undo_files")


def mentions_files(text) -> bool:
    return bool(_FILES.search(text or ""))


def mentions_board(text) -> bool:
    return bool(_BOARD.search(text or ""))


def pick_tools(text, limit=12, exclude=()):
    """Names of the tools that look relevant to what he said (plus CORE_TOOLS),
    so a model with a small token budget isn't sent all of them. Scores each
    tool by the words its name and description share with the request."""
    said = _words(text)
    scored = []
    for s in SKILLS:
        if s["name"] in exclude:
            continue
        name_words = set(s["name"].split("_"))
        score = 3 * len(said & name_words) + len(said & _words(s["description"]))
        if score:
            scored.append((score, s["name"]))
    scored.sort(key=lambda x: -x[0])
    keep = {n for _, n in scored[:limit]}
    if mentions_board(text):
        keep |= set(BOARD_TOOLS)
    if mentions_files(text):
        keep |= set(FILE_TOOLS)
    if _DOCS.search(text or ""):
        keep |= set(DOC_TOOLS) | {"find_files", "read_file"}
    keep -= set(exclude)
    return keep | {n for n in CORE_TOOLS if n in _BY_NAME and n not in exclude}


# ---------- spoken progress ----------
# Long tools shouldn't leave him in silence (idea from OpenLive's narrated
# progress). main.py sets a handler for the thread running a spoken turn; a
# tool that runs longer than PROGRESS_AFTER gets a short filler line, and any
# tool can narrate its own steps with skills.progress("Opening Chrome now.").
PROGRESS_AFTER = 4.0
PROGRESS_EVERY = 25.0
FILLERS = {
    "use_computer": "Working on it, sir.",
    "look_at_screen": "Having a look, sir.",
    "whats_the_buzz": "Seeing what people are saying, sir.",
    "web_search": "Searching now, sir.",
    "find_files": "Looking through your files, sir.",
    "organize_folder": "Going through the folder, sir.",
    "make_document": "Writing it up now, sir.",
    "check_email": "Checking your email, sir.",
    "daily_briefing": "Pulling that together, sir.",
    "show_diagram": "Drawing that up for you, sir.",
}
_local = threading.local()


def set_progress_handler(handler):
    """handler(text) speaks a short line now; None turns it off (for this thread)."""
    _local.handler = handler


def progress(text: str):
    """Say a short progress line, if this turn is being spoken."""
    handler = getattr(_local, "handler", None)
    if handler and text:
        try:
            handler(text)
        except Exception as e:
            print(f"[progress] {e}")


def _watch_progress(name, done, handler):
    if done.wait(PROGRESS_AFTER):
        return
    handler(FILLERS.get(name, "One moment, sir."))
    while not done.wait(PROGRESS_EVERY):
        handler("Still working on it, sir.")


# Tools whose results are our own words, not outside content (skip the injection scan).
TRUSTED_RESULTS = {"set_timer", "set_alarm", "list_timers", "cancel_timer", "set_reminder", "list_reminders",
                   "cancel_reminder", "remember", "forget", "get_settings", "change_setting", "list_jobs",
                   "try_offline_voice"}


def _guard():
    """This thread's loop guard, fresh for each conversation turn."""
    from brain.safety import LoopGuard
    g = getattr(_local, "guard", None)
    if g is None or getattr(_local, "guard_turn", None) != turn:
        g = _local.guard = LoopGuard()
        _local.guard_turn = turn
    return g


# Tools that can't work without the internet; offline they say so at once
# instead of waiting on a timeout.
NEEDS_INTERNET = {"get_weather", "get_news", "web_search", "whats_the_buzz", "get_calendar_events",
                  "check_email", "reply_email", "add_calendar_event", "delete_calendar_event", "stock_price", "look_at_screen",
                  "use_computer", "plan_claude_code_task", "start_claude_code_task", "edit_selected_text",
                  "daily_briefing", "open_website", "show_diagram", "make_document"}


def run(name: str, args: dict) -> str:
    skill = _BY_NAME.get(name)
    if skill is None:
        return f"Unknown tool {name}."
    if name in NEEDS_INTERNET:
        from brain import network
        if not network.online():
            return f"The internet is down, so {name} can't work right now. Tell him briefly."
    from brain import safety
    verdict, note = _guard().check(name, args)
    if verdict == "block":
        return note
    done = threading.Event()
    handler = getattr(_local, "handler", None)
    if handler:
        threading.Thread(target=_watch_progress, args=(name, done, handler), daemon=True).start()
    try:
        print(f"[tool] {name} {args}")
        result = str(skill["run"](args or {}))
        print(f"[tool] -> {result[:150].replace(chr(10), ' | ')}")
        if name not in TRUSTED_RESULTS:
            result = safety.guard_content(result, name)
        return result + note
    except Exception as e:
        print(f"[tool] {name} failed: {e}")
        return f"The {name} tool failed: {e}"
    finally:
        done.set()
