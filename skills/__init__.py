"""Jarvis's skills (tools the language model can call).

Each skill module exposes SKILLS: a list of dicts with
    name, description, parameters (JSON Schema), run(args) -> str
That's provider-neutral: anthropic_tools() and openai_tools() turn it into the
format Claude or an OpenAI-style API (Groq, OpenAI, Ollama...) expects.
"""
import re
import threading

import ui_events

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
from skills import cad  # noqa: E402
from skills import web_search  # noqa: E402
from skills import background  # noqa: E402
from skills import study  # noqa: E402
from skills import clipboard_tools  # noqa: E402
from skills import sticky  # noqa: E402
from skills import calculator  # noqa: E402
from skills import canvas  # noqa: E402
from skills import recap  # noqa: E402
from skills import vocab  # noqa: E402
from skills import viewer3d  # noqa: E402
from skills import workspace  # noqa: E402
from skills import sight  # noqa: E402
from skills import browser_bridge  # noqa: E402,F401
from skills import phone  # noqa: E402
from skills import pointer  # noqa: E402

MODULES = [
    briefing,
    memory_tools,
    vocab,
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
    cad,
    viewer3d,
    workspace,
    sight,
    personality,
    background,
    study,
    clipboard_tools,
    sticky,
    calculator,
    canvas,
    recap,
    phone,
    pointer,
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
_CAD = _re.compile(r"\b(3d|three d|print(?:able)?|printer|openscad|scad|stl|cad|bracket|enclosure|phone stand|"
                   r"mount|model (?:of|for)|taller|shorter|wider|thicker|thinner)\b", _re.I)
CAD_TOOLS = ("make_3d_model", "show_3d_model", "open_in_openscad")
_APPS = _re.compile(r"\b(claude code|(?:build|make|code|write|create) (?:me )?(?:a |an )?(?:little |small |simple |quick )?"
                    r"[\w -]{0,25}?\b(?:app|application|website|web ?page|web ?site|game|tool|program|widget|tracker|"
                    r"calculator|timer app)|my [\w -]{1,25} app)\b", _re.I)
APP_TOOLS = ("plan_new_app", "plan_claude_code_task", "start_claude_code_task", "claude_code_status")
# A tool used last turn that needs another one when he says yes.
FOLLOW_UPS = {"plan_new_app": ("start_claude_code_task",), "plan_claude_code_task": ("start_claude_code_task",)}
FILE_TOOLS = ("make_file", "find_files", "read_file", "open_file", "organize_folder", "file_action", "undo_files")


def mentions_files(text) -> bool:
    return bool(_FILES.search(text or ""))


def mentions_board(text) -> bool:
    return bool(_BOARD.search(text or ""))


_MATHS = re.compile(r"\d\s*[-+*/x^]\s*\d|\b(times|divided|plus|minus|squared|sqrt|square root|percent|"
                    r"convert|how many|calculate|work out|what'?s \d)\b|\d\s*(?:k?N|[kMG]?Pa|kWh?|psi|mm|cm|km|kg|"
                    r"lbs?|ft|°|deg|kelvin|celsius|fahrenheit)\b", re.I)
_CLIP = re.compile(r"\b(copied|clipboard|what i (?:just )?copied|translate|paste)\b", re.I)
_STUDY = re.compile(r"\b(quiz|flash ?cards?|pomodoro|study|studying|revise|revision|focus (?:session|time|mode))\b", re.I)
# "what are you working on", "is it done", "cancel that", "stop the task"
_CANVAS = re.compile(r"\b(canvas|class files|course files|lecture (?:notes|slides|files)|my (?:classes|courses)|"
                     r"due|assignments?|homework|deadlines?)\b", re.I)
CANVAS_TOOLS = ("canvas_setup", "canvas_sign_in", "canvas_courses", "canvas_download", "canvas_due")
_SCREEN = re.compile(r"\b(screen|looking at|this page|this site|web ?page|website|tab|selected|selection|"
                     r"read (?:me )?(?:this|that|it)|error|dialog|inspect|page code|source code|html|the code)\b", re.I)
_VISUAL = re.compile(r"\b(picture|photo|image|video|diagram|chart|graph|drawing|looks? like|colou?rs?|layout|design|"
                     r"screenshot|icon|logo|meme|map)\b", re.I)
_BRIEF = re.compile(r"\b(brief|article|what i have up|i have (?:up|open)|summari[sz]e|summary|outline|tl;?dr|this (?:article|page|pdf|paper|document|doc)|"
                    r"the brief|section \d|sections?|reader|lab manual)\b", re.I)
BRIEF_TOOLS = ("brief_document", "edit_brief", "read_brief", "save_brief_as_word", "view_document")
_RECAP = re.compile(r"\b(what did (?:i|we) do|recap|my day|today so far|what have i (?:done|been doing))\b", re.I)
_TASKS = re.compile(r"\b(working on|doing|busy|done yet|finished|progress|status|cancel|stop|abort|tasks?|jobs?)\b", re.I)


BRIEF_INTENT = re.compile(
    r"\b(?:brief|breathe|summari[sz]e|sum\s+up|tl;?dr)\s+(?:me\s+on\s+)?(?:this|that|it|the\s+(?:article|page|story|"
    r"pdf|document|doc|paper|post)|what\s+i(?:'m|\s+am)\s+(?:reading|looking\s+at)|what\s+i\s+have\s+(?:up|open))\b"
    r"|\b(?:write|make|create|give|do)\s+(?:me\s+)?(?:a\s+|the\s+)?(?:brief|summary|tl;?dr)\b"
    r"(?!\s+(?:of|on|about|for)\s+(?:my|the|today|this\s+week)\b(?!\s+(?:article|page|story|pdf|document|doc|paper)))",
    re.I)
_BRIEF_EDIT = re.compile(r"\b(?:change|edit|add|remove|shorter|longer|save|read|rewrite|update|fix)\b", re.I)


_SCREEN_REF = re.compile(
    r"\b(?:this|that)\s+(?:article|page|web\s?page|website|site|story|post|pdf|document|doc|paper|tab|thing\s+here)\b"
    r"|\bon\s+(?:my|the)\s+screen\b|\b(?:i\s+have|i've\s+got|that's)\s+(?:up|open)\b|\barticle\s+(?:here|up)\b"
    r"|\bwhat\s+i(?:'m|\s+am)\s+(?:reading|looking\s+at)\b|\b(?:off|from)\s+(?:of\s+)?my\s+screen\b", re.I)
_SCREEN_FOLLOWUP = re.compile(r"\b(?:it|this|that|the article|the page|on it|about it|from it)\b", re.I)


def screen_intent(text: str) -> bool:
    """He refers to what's on his screen ("make slides on this article", "use what I have up")."""
    return bool(_SCREEN_REF.search(text or ""))


def mentions_screen_followup(text: str) -> bool:
    return bool(_SCREEN_FOLLOWUP.search(text or ""))


_RESTYLE = re.compile(r"\b(?:pretty|prettier|nicer|better[- ]looking|look(?:s)? (?:better|nicer|good)|corporate|"
                      r"professional|theme|style|design|colou?rs?|colou?rful|darker|lighter|sleek|modern|minimal|"
                      r"purple|green|blue|orange|repetitive|boring|plain|bland|same every)\b", re.I)


def restyle_intent(text: str) -> bool:
    """ "Make it prettier", "make it corporate": a new look for the deck he just made, not a new deck."""
    from skills import documents
    t = text or ""
    if not _RESTYLE.search(t) or re.search(r"\b(?:new|another)\s+(?:deck|presentation|slides|document)\b", t, re.I):
        return False
    if re.search(r"\b(?:about|on)\s+(?!it\b|this\b|that\b|them\b|the\s+(?:deck|slides|slideshow))\w", t, re.I):
        return False   # "a corporate deck about cyber security" is a new one
    if not re.search(r"\b(?:it|this|that|them|the\s+(?:deck|slides?|slideshow|presentation|document|doc|powerpoint))\b",
                     t, re.I) and len(t.split()) > 4:
        return False
    return documents.last() is not None or bool(documents.open_office_files())


SCRIPT_INTENT = re.compile(
    r"\b(?:script|speech|speaker\s+notes|presenter\s+notes|talking\s+points|what\s+(?:to|should\s+i|do\s+i)\s+say)\b"
    r".{0,40}\b(?:slides?|slideshow|slide\s*deck|deck|presentation|powerpoint|it|this|that)\b"
    r"|\b(?:slides?|slideshow|deck|presentation|powerpoint)\b.{0,30}\b(?:script|speech|speaker\s+notes)\b", re.I)


def script_intent(text: str) -> bool:
    """ "Make a script for the slideshow", "write me speaker notes for this presentation"."""
    from skills import documents
    if not SCRIPT_INTENT.search(text or "") or re.search(r"\b(?:python|code|bash|powershell|autohotkey)\b", text or "", re.I):
        return False
    return documents.last() is not None or bool(documents.open_office_files()) or \
        bool(re.search(r"\.pptx\b|\b(?:called|named)\b", text or "", re.I))


EMAIL_INTENT = re.compile(
    r"\b(?:any|unread|new|check|read|got|have\s+i\s+got|what(?:'s| is)\s+in)\b.{0,25}\b(?:e-?mails?|inbox|gmail|mail)\b"
    r"|\b(?:e-?mails?|inbox)\b.{0,15}\b(?:today|unread|new)\b", re.I)


def email_intent(text: str) -> bool:
    """ "Any unread emails?", "check my inbox" (not "write an email to...")."""
    t = text or ""
    return bool(EMAIL_INTENT.search(t)) and not re.search(r"\b(?:send|write|reply|draft|forward|compose)\b", t, re.I)


GUIDE_NEXT = re.compile(r"^\W*(?:(?:ok(?:ay)?|alright|right|cool|done|got it|yep|yes)\W*)*(?:next(?: step| one)?|"
                        r"(?:i(?:'ve| have)? )?done(?: that| it)?|what(?:'s| is)? next|what now|then what|go back|"
                        r"(?:show me )?(?:that )?again|repeat that)\W*$", re.I)
POINT_WORDS = re.compile(r"\b(?:where(?:'s| is| are| do i find)|point (?:at|to|out)|show me (?:where|the|which)|"
                         r"which (?:one|button|icon|option)|can't find|how do i|show me how to|walk me through)\b", re.I)


def route(text: str) -> dict:
    """What's decided before the model sees a request (the model can't get these wrong):
    direct: [(tool, args)] to run straight away; exclude: tools the model mustn't use this turn;
    screen: read his screen first because he said "this article" / "on my screen"."""
    plan = {"direct": [], "exclude": set(), "screen": False, "followup": False}
    if phone_test_intent(text):
        plan["direct"].append(("test_phone_alerts", {}))
        plan["exclude"].add("test_phone_alerts")
    if restyle_intent(text):
        plan["exclude"] |= {"make_document", "restyle_document"}   # a new look, never a new deck
        plan["direct"].append(("restyle_document", {"style": text or ""}))
    elif script_intent(text):
        plan["direct"].append(("write_script", {"details": text or ""}))
        plan["exclude"] |= {"write_script", "make_document", "make_file"}
    if pointer.guide_active() and GUIDE_NEXT.match(text or ""):
        plan["direct"].append(("guide_back" if re.search(r"\b(?:back|again|repeat)\b", text or "", re.I)
                               else "guide_next", {}))
        plan["exclude"] |= {"guide_next", "guide_back", "whiteboard_step"}
    if email_intent(text):
        plan["direct"].append(("check_email", {}))
        plan["exclude"].add("check_email")
    searching = re.search(r"\b(?:search|look (?:\w+ )?up|google|online|on the web|internet)\b", text or "", re.I)
    if brief_intent(text):
        plan["direct"].append(("brief_document", {"source": ""}))
        plan["exclude"] |= {"brief_document", "web_search", "look_at_screen"}   # it's already being read
    elif screen_intent(text):
        plan["screen"] = True
        if not searching:
            plan["exclude"].add("web_search")     # "this" is on his screen, not on the web
    elif sight.recent() and mentions_screen_followup(text) and not searching:
        plan["followup"] = True                   # "now make slides on it": the page he just had read
        plan["exclude"].add("web_search")
    return plan


def phone_test_intent(text: str) -> bool:
    """ "Test my phone notifications", "send a test alert to my phone"."""
    return bool(re.search(r"\btest\w*\b.{0,25}\b(?:phone|notifications?|alerts?|telegram|call)\b", text or "", re.I))


def brief_intent(text: str) -> bool:
    """He wants what's on his screen briefed ("brief this article", "write me a brief")."""
    t = text or ""
    if not BRIEF_INTENT.search(t) or re.search(r"https?://|\.(?:pdf|docx?|pptx|txt|md)\b", t, re.I):
        return False
    if _BRIEF_EDIT.search(t):
        with workspace._lock:
            if workspace._ws.get("doc"):
                return False   # a brief is open: he's asking to change it (edit_brief)
    return True


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
    if _APPS.search(text or ""):
        keep |= set(APP_TOOLS)
    if _CAD.search(text or ""):
        keep |= set(CAD_TOOLS)
    if _DOCS.search(text or ""):
        keep |= set(DOC_TOOLS) | {"find_files", "read_file"}
    if _MATHS.search(text or ""):
        keep.add("calculate")
    if _CLIP.search(text or ""):
        keep |= {"read_clipboard", "copy_to_clipboard"}
    if _STUDY.search(text or ""):
        keep |= {"quiz_me", "quiz_next", "pomodoro", "find_files"}
    if _CANVAS.search(text or ""):
        keep |= set(CANVAS_TOOLS)
    if re.search(r"\b(?:test|try)\b.*\b(?:phone|call|telegram|alerts?)\b", text or "", re.I):
        keep.add("test_phone_alerts")
    if POINT_WORDS.search(text or ""):
        keep |= {"point_at", "show_me_how"}
    if pointer.guide_active():
        keep |= {"guide_next", "guide_back", "hide_pointer"}
    if restyle_intent(text):
        keep.add("restyle_document")
        keep.discard("make_document")
    if re.search(r"\b(?:split|side by side|next to each other|half (?:the|my) screen|snap)\b", text or "", re.I):
        keep.add("split_screen")
    if screen_intent(text):
        keep |= {"read_screen", "make_document", "quiz_me"}
    if _SCREEN.search(text or "") or _BRIEF.search(text or ""):
        keep.add("read_screen")
    if _VISUAL.search(text or ""):
        keep.add("look_at_screen")    # paid: only for pictures and looks, never plain text
    else:
        keep.discard("look_at_screen")
    if _BRIEF.search(text or ""):
        keep |= set(BRIEF_TOOLS)
    if _RECAP.search(text or ""):
        keep.add("daily_recap")
    if _TASKS.search(text or "") and background.active():
        keep |= {"list_tasks", "cancel_task"}
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
    "read_screen": "Having a look, sir.",
    "whats_the_buzz": "Seeing what people are saying, sir.",
    "web_search": "Searching now, sir.",
    "find_files": "Looking through your files, sir.",
    "organize_folder": "Going through the folder, sir.",
    "make_document": "Writing it up now, sir.",
    "check_email": "Checking your email, sir.",
    "daily_briefing": "Pulling that together, sir.",
    "show_diagram": "Drawing that up for you, sir.",
    "canvas_download": "Fetching your class files from Canvas, sir.",
    "brief_document": "Reading it now, sir.",
    "edit_brief": "Changing that now, sir.",
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
                  "use_computer", "plan_claude_code_task", "start_claude_code_task", "plan_new_app", "edit_selected_text",
                  "daily_briefing", "open_website", "show_diagram", "make_document", "make_3d_model",
                  "brief_document", "edit_brief"}


# What the chip next to the orb says while a tool runs. Quick lookups
# (time, timers, memory) show nothing: a chip that flashes is just noise.
TASK_LABELS = {
    "open_app": "Opening {name}", "open_website": "Opening {url}", "open_file": "Opening the file", "open_folder": "Opening {folder}",
    "use_computer": "Working on the screen", "look_at_screen": "Looking at the screen", "read_screen": "Reading the screen",
    "web_search": "Searching the web", "get_weather": "Checking the weather", "get_news": "Getting the news",
    "check_email": "Checking email", "get_calendar_events": "Checking the calendar",
    "show_diagram": "Drawing on the whiteboard", "make_document": "Making the document",
    "make_3d_model": "Designing the 3D part", "organize_folder": "Sorting {folder}", "play_music": "Starting the music", "daily_briefing": "Getting your briefing",
    "plan_new_app": "Planning the app", "start_claude_code_task": "Starting Claude Code",
    "brief_document": "Writing the brief", "edit_brief": "Editing the brief",
}


def task_label(name: str, args: dict) -> str:
    label = TASK_LABELS.get(name)
    if not label:
        return ""
    fields = {k: str(v)[:28] for k, v in (args or {}).items() if isinstance(v, (str, int, float))}
    try:
        label = label.format(**fields)
    except (KeyError, IndexError):
        label = re.sub(r" ?\{\w+\}", "", label)
    return label + "..."


def run(name: str, args: dict) -> str:
    skill = _BY_NAME.get(name)
    if skill is None:
        return f"Unknown tool {name}."
    if name in NEEDS_INTERNET:
        from brain import network
        if not network.online():
            return f"The internet is down, so {name} can't work right now. Tell him briefly."
    verdict, note = _guard().check(name, args)
    if verdict == "block":
        return note
    label = task_label(name, args)
    handler = getattr(_local, "handler", None)
    if background.wants(name, args or {}, live=handler is not None):
        # A long job: it runs on its own thread and he can talk to Jarvis meanwhile.
        return background.start(name, args or {}, lambda a: _call(skill, name, a), label) + note
    done = threading.Event()
    if handler:
        threading.Thread(target=_watch_progress, args=(name, done, handler), daemon=True).start()
    ok = False
    if label:
        ui_events.task(label)
    try:
        result = _call(skill, name, args)
        ok = True
        return result + note
    except Exception as e:
        print(f"[tool] {name} failed: {e}")
        return f"The {name} tool failed: {e}"
    finally:
        done.set()
        if label:
            ui_events.task_done(ok)


def _call(skill, name, args):
    from brain import safety
    print(f"[tool] {name} {args}")
    result = str(skill["run"](args or {}))
    print(f"[tool] -> {result[:150].replace(chr(10), ' | ')}")
    if name not in TRUSTED_RESULTS:
        result = safety.guard_content(result, name)
    return result
