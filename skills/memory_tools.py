"""remember / forget: long-term facts about the user (stored by brain.memory)."""
from brain import memory

SKILLS = [
    {
        "name": "remember",
        "description": (
            "Save a lasting fact about the user so you know it in future conversations, "
            "e.g. names of people, preferences, routines, birthdays, home city. Use it when the "
            "user asks you to remember something, or tells you a personal detail worth keeping. "
            "Write the fact as a short standalone sentence about the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {"fact": {"type": "string"}},
            "required": ["fact"],
        },
        "run": lambda a: memory.add_fact(a.get("fact", "")),
    },
    {
        "name": "forget",
        "description": (
            "Delete saved facts that contain the given words, when the user asks you to "
            "forget something or says a saved fact is wrong."
        ),
        "parameters": {
            "type": "object",
            "properties": {"about": {"type": "string", "description": "Words the fact contains"}},
            "required": ["about"],
        },
        "run": lambda a: memory.remove_facts(a.get("about", "")),
    },
]
