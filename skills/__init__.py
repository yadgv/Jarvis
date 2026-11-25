"""Jarvis's skills (tools the language model can call).

Each skill module exposes SKILLS: a list of dicts with
    name, description, parameters (JSON Schema), run(args) -> str
That's provider-neutral: anthropic_tools() and openai_tools() turn it into the
format Claude or an OpenAI-style API (Groq, OpenAI, Ollama...) expects.
"""
from skills import (calendar_events, computer, icloud_calendar, memory_tools, news, pc_control, reminders, screen,
                    stocks, system, timers, weather, web_search)

SKILLS = [*memory_tools.SKILLS, *timers.SKILLS, *reminders.SKILLS, *weather.SKILLS, *news.SKILLS, *web_search.SKILLS,
          *calendar_events.SKILLS, *icloud_calendar.SKILLS, *stocks.SKILLS, *pc_control.SKILLS, *screen.SKILLS,
          *computer.SKILLS, *system.SKILLS]
_BY_NAME = {s["name"]: s for s in SKILLS}


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
