"""Play a song, artist, album or playlist by name in the Apple Music app.

Apple Music for Windows has no API to start a track, so Jarvis opens the app
and first drives it through its buttons' names (UI Automation, no screenshots).
If that can't find the song, it falls back to screen control (use_computer),
which needs Claude and takes several seconds. Pause/skip/volume use the media
keys instead (the 'media' skill), which is instant.
"""
import re
import time

import config
from skills import computer, pc_control, ui_automation
from skills.quick_actions import log_tier

KINDS = ("song", "artist", "album", "playlist")


def play_music(a):
    query = (a.get("query") or "").strip()
    if not query:  # "play some music": the media key resumes whatever was on, instantly
        return pc_control.media({"action": "play"})
    kind = (a.get("kind") or "song").strip().lower()
    if kind not in KINDS:
        kind = "song"
    if re.search(r"\byoutube\b", query, re.I) or a.get("where") == "youtube":
        return _on_youtube(re.sub(r"\s*\b(?:on|in)?\s*youtube\b", "", query, flags=re.I))
    opened = pc_control.open_app({"name": config.MUSIC_APP})
    if not opened.startswith("Opened"):
        return _on_youtube(query)
    time.sleep(config.MUSIC_OPEN_WAIT)  # give the app a moment to come to the front
    # Tier 2: the app's own buttons by name (no screenshots, no big model).
    played = ui_automation.play_in_app(config.MUSIC_APP, query)
    if played:
        return f"Playing: {played}."
    if not getattr(config, "MUSIC_SCREEN_CONTROL", False):
        # Screen control costs money (Claude): play it on YouTube in his browser instead, for free.
        return _on_youtube(query)
    log_tier(3, f"play_music '{query}' falls back to screen control")
    where = ("Look in his Library > Playlists first; if it isn't there, search Apple Music. "
             if kind == "playlist" else "")
    task = (
        f"The {config.MUSIC_APP} app has just been opened (bring its window to the front if needed). "
        f"Play the {kind} '{query}'. {where}Click the search box, type the name, press Enter, pick the best "
        f"matching {kind} in the results and start it playing (for an artist, play their top songs). "
        "Playing music is harmless: no need to ask for confirmation. Don't change any settings, sign in, "
        "or buy anything. When it's playing, reply with just the title and artist."
    )
    return computer.use_computer({"task": task})


def _on_youtube(query):
    from skills import quick_actions
    out = quick_actions.open_website({"site": "youtube", "search": query, "play": True})
    return f"{config.MUSIC_APP} couldn't play it, so: {out} Tell him it's playing on YouTube."


SKILLS = [
    {
        "name": "play_music",
        "description": (
            "Play a specific song, artist, album or playlist by name in Apple Music, e.g. 'play Blinding "
            "Lights', 'play some Drake', 'put on my workout playlist'. 'On YouTube': use open_website "
            "(site youtube, play=true) instead. For pause, resume, next or previous "
            "use the media tool instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name to search for, e.g. 'Blinding Lights The Weeknd'"},
                "kind": {"type": "string", "enum": list(KINDS)},
            },
            "required": ["query"],
        },
        "run": play_music,
    },
]
