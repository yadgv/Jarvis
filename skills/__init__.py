"""Jarvis's skills (tools the language model can call).

Each skill module exposes SKILLS: a list of dicts with
    name, description, parameters (JSON Schema), run(args) -> str
That's provider-neutral: anthropic_tools() and openai_tools() turn it into the
format Claude or an OpenAI-style API (Groq, OpenAI, Ollama...) expects.
"""
from skills import calendar_events, memory_tools, pc_control, stocks, system, timers, weather, web_search

SKILLS = [*memory_tools.SKILLS, *timers.SKILLS, *weather.SKILLS, *web_search.SKILLS,
          *calendar_events.SKILLS, *stocks.SKILLS, *pc_control.SKILLS, *system.SKILLS]
_BY_NAME = {s["name"]: s for s in SKILLS}


def anthropic_tools():
    return [
        {"name": s["name"], "description": s["description"], "input_schema": s["parameters"]}
        for s in SKILLS
    ]


def openai_tools():
    return [
        {"type": "function",
         "function": {"name": s["name"], "description": s["description"], "parameters": s["parameters"]}}
        for s in SKILLS
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
