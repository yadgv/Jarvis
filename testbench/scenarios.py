"""Conversations for talk_tests.py: a second AI plays ziad, with a goal, and
talks to Jarvis until it's done (or gives up). A third call grades the chat.

Each scenario:
  goal     what "he" wants by the end, in his words
  opener   his first line (so every run starts the same way)
  expect   tools Jarvis should have used at some point (all of them)
  avoid    tools he must never use in it
  screen / last_doc   what's on his screen / the deck he just made (as in cases.py)
  turns    at most this many things he says (default 5)
"""

SCENARIOS = [
    {"id": "article-to-slides", "screen": "cbc",
     "goal": "Get a short brief of the news article on your screen, then slides made on it, then make the slides "
             "look corporate.",
     "opener": "Hey, can you brief this article for me?",
     "expect": ["brief_document", "make_document", "restyle_document"], "avoid": ["web_search"], "turns": 6},
    {"id": "study-session",
     "goal": "Find out what's due on Canvas this week, then get quizzed on thermodynamics for two questions.",
     "opener": "What do I have due this week?",
     "expect": ["canvas_due", "quiz_me"]},
    {"id": "arduino-help",
     "goal": "Learn how to wire an LED to an Arduino step by step on the whiteboard, then get a 3D printable case "
             "for an Arduino Uno.",
     "opener": "Can you show me how to wire an LED to my Arduino?",
     "expect": ["show_diagram", "make_3d_model"], "turns": 6},
    {"id": "music-and-timer",
     "goal": "Play Blinding Lights, turn the volume down a bit, and set a 25 minute timer to study.",
     "opener": "Play Blinding Lights",
     "expect": ["play_music", "set_volume", "set_timer"], "avoid": ["use_computer"]},
    {"id": "tidy-downloads",
     "goal": "Get your downloads folder sorted, then change your mind and have it undone.",
     "opener": "My downloads folder is a mess, can you sort it out?",
     "expect": ["organize_folder", "undo_files"]},
    {"id": "evening-plan",
     "goal": "Check tomorrow's calendar and the weather in Courtice, and set a reminder to call mom at 6 pm, then "
             "say goodbye.",
     "opener": "What's on my calendar tomorrow?",
     "expect": ["get_calendar_events", "get_weather", "set_reminder"]},
    {"id": "vague-presentation",
     "goal": "You want a presentation but at first don't say on what. When Jarvis asks, say it's on renewable "
             "energy for a grade 12 class.",
     "opener": "Can you make me a presentation?",
     "expect": ["make_document"]},
]

# How "he" talks: what the simulated user is told.
PERSONA = (
    "You are Ziad, a university engineering student in Courtice, Ontario, talking out loud to Jarvis, his voice "
    "assistant, which runs on his Windows PC. Speak like a real person talking to a voice assistant: short, "
    "casual, one sentence, sometimes a bit vague, no emojis, no stage directions. You never explain that you "
    "are testing anything. Work toward your goal one step at a time, reacting to what Jarvis just said "
    "(answer his questions, correct him if he got it wrong). When the whole goal is done, or Jarvis clearly "
    "can't do it after you've asked twice, say a short natural goodbye like \"cool, that's everything, thanks\" "
    "and then on the next turn reply with exactly <done>.\n\nYour goal: {goal}"
)

JUDGE = (
    "You grade a voice assistant called Jarvis from a transcript. The user had this goal: {goal}\n"
    "Tools are dry runs: a tool listed as used counts as done. Judge only Jarvis's side. Reply with JSON only, "
    "no other text: {{\"goal_done\": true|false, \"score\": 1-5, \"problems\": [\"short sentence\", ...]}}. "
    "Score 5 = did everything right and sounded natural; 3 = got there with friction (repeated questions, "
    "wrong tool first, waffle); 1 = failed or said something false (claimed something it didn't do, invented "
    "facts, read out tool notes or code). Keep problems specific, at most 4."
)
