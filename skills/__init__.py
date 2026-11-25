"""Jarvis's skills (tools the language model can call).

Each skill module exposes SKILLS: a list of dicts with
    name, description, parameters (JSON Schema), run(args) -> str
That's provider-neutral: anthropic_tools() and openai_tools() turn it into the
format Claude or an OpenAI-style API (Groq, OpenAI, Ollama...) expects.
"""
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
from skills import memory_tools  # noqa: E402
from skills import music  # noqa: E402
from skills import news  # noqa: E402
from skills import pc_control  # noqa: E402
from skills import quick_actions  # noqa: E402
from skills import personality  # noqa: E402
from skills import reminders  # noqa: E402
from skills import screen  # noqa: E402
from skills import stocks  # noqa: E402
from skills import system  # noqa: E402
from skills import timers  # noqa: E402
from skills import ui_automation  # noqa: E402
from skills import weather  # noqa: E402
from skills import web_search  # noqa: E402

MODULES = [
    briefing,
    memory_tools,
    timers,
    reminders,
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


def openai_tools(exclude=()):
    return [
        {"type": "function",
         "function": {"name": s["name"], "description": s["description"], "parameters": s["parameters"]}}
        for s in SKILLS if s["name"] not in exclude
    ]


def run(name: str, args: dict) -> str:
    skill = _BY_NAME.get(name)
    if skill is None:
        return f"Unknown tool {name}."
    try:
        print(f"[tool] {name} {args}")
        result = str(skill["run"](args or {}))
        print(f"[tool] -> {result[:150].replace(chr(10), ' | ')}")
        return result
    except Exception as e:
        print(f"[tool] {name} failed: {e}")
        return f"The {name} tool failed: {e}"
