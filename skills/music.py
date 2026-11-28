"""Play a song, artist, album or playlist by name in the Apple Music app.

Apple Music for Windows has no API to start a track, so Jarvis opens the app
and first drives it through its buttons' names (UI Automation, no screenshots).
If that can't find the song, it falls back to screen control (use_computer),
which needs Claude and takes several seconds. Pause/skip/volume use the media
keys instead (the 'media' skill), which is instant.
"""
import difflib
import re
import time

import config
from skills import computer, pc_control, ui_automation
from skills.quick_actions import log_tier

KINDS = ("song", "artist", "album", "playlist")


# ---------- "Play some music" -> "One of your playlists?" ----------
OFFER_SECONDS = 120          # how long his answer to the question counts as an answer
_offer = {"at": 0.0}
_GENERIC = re.compile(
    r"^\W*(?:(?:hey |ok |okay )?jarvis\W*)?(?:(?:can|could|would|will) you |please |i (?:want|need) (?:you )?to |"
    r"i wanna |let'?s |go ahead and |just )?(?:play|put on|start|throw on|blast|listen to|hear)"
    r"(?: me| us| for me)?(?: some| a little| any| a bit of)?(?: (?:music|songs?|tunes|something))(?: for me)?"
    r"(?: (?:please|now|jarvis))*\W*$|"
    r"^\W*(?:(?:some )?music|tunes),? please\W*$|^\W*i (?:want|wanna|would like|'d like) (?:to listen to |some )?"
    r"(?:some )?music\W*$", re.I)
_DECLINE = re.compile(r"^\W*(?:no|nah|nope|neither|none(?: of (?:them|those))?|not (?:really|those|now)|"
                      r"something else|anything|whatever|random|surprise me|you (?:pick|choose)|"
                      r"just (?:play|put on|resume) (?:something|anything|whatever|music|what was on))\b", re.I)
_ALIASES = {"quran": ("koran", "quoran", "kuran", "qur'an", "qoran")}
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "last": -1}
_COMMON = {"playlist", "music", "songs", "mix"}


def playlists():
    return [p for p in getattr(config, "MY_PLAYLISTS", []) if p.strip()]


def offer_intent(text: str) -> bool:
    """ "Play some music", "put on music", "can you play me something": nothing named, so he's asked first."""
    return bool(playlists()) and bool(_GENERIC.match(text or ""))


def offer_question() -> str:
    names = playlists()
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f", or {names[-1]}"
    _offer["at"] = time.time()
    return f"Want one of your playlists? {listed}?"


def offer_open() -> bool:
    return bool(_offer["at"]) and time.time() - _offer["at"] < OFFER_SECONDS


def _key(name):
    words = re.findall(r"[a-z0-9']+", name.lower())
    return [w for w in words if w != "the"] or words


def pick_playlist(text: str):
    """Which of his playlists he named in text ("Performative", "the Quran one", "the first one"), or None."""
    names = playlists()
    said = re.findall(r"[a-z0-9']+", (text or "").lower())
    found = []
    for name in names:
        key = _key(name)
        options = {" ".join(key), *_ALIASES.get(" ".join(key), ())}
        for opt in options:
            n = len(opt.split())
            grams = [" ".join(said[i:i + n]) for i in range(len(said) - n + 1)]
            if opt in grams or difflib.get_close_matches(opt, grams, n=1, cutoff=0.8):
                found.append(name)
                break
    if len(found) > 1:   # "the Quran playlist": "playlist" is the common word, Quran is the name
        found = [n for n in found if " ".join(_key(n)) not in _COMMON] or found
    if found:
        return found[0]
    picks = [_ORDINALS[w] for w in said if w in _ORDINALS]
    if picks and -len(names) <= picks[0] < len(names):   # "the first one", "the last one"
        return names[picks[0]]
    return None


def answer_offer(text: str):
    """His answer to "Want one of your playlists?": ("playlist", name), ("decline", None), or None when he
    asked for something else ("play some Drake"), which then goes the usual way."""
    if not offer_open():
        return None
    _offer["at"] = 0.0
    name = pick_playlist(text)
    if name:
        return "playlist", name
    if _DECLINE.match(text or "") or re.fullmatch(r"\W*(?:no|nah|nope)\W*(?:thanks|thank you)?\W*", text or "", re.I):
        return "decline", None
    return None


def play_playlist(name: str) -> str:
    """One of his own saved playlists, by its name in his Library (not a search of all of Apple Music)."""
    opened = pc_control.open_app({"name": config.MUSIC_APP})
    if not opened.startswith("Opened"):
        return f"I couldn't open {config.MUSIC_APP} to play {name}."
    time.sleep(config.MUSIC_OPEN_WAIT)
    played = ui_automation.play_library_playlist(config.MUSIC_APP, name)
    if played:
        return f"Playing {name}."
    return play_music({"query": name, "kind": "playlist", "_opened": True})


def play_music(a):
    query = (a.get("query") or "").strip()
    if not query:
        if playlists() and not a.get("resume"):
            # "Play some music" with nothing named: his own playlists first (his answer is handled directly).
            return f"Ask him, in these words: {offer_question()}"
        return pc_control.media({"action": "play"})   # the media key resumes whatever was on, instantly
    kind = (a.get("kind") or "song").strip().lower()
    if kind not in KINDS:
        kind = "song"
    if re.search(r"\byoutube\b", query, re.I) or a.get("where") == "youtube":
        return _on_youtube(re.sub(r"\s*\b(?:on|in)?\s*youtube\b", "", query, flags=re.I))
    if kind == "playlist" and not a.get("_opened"):
        mine = next((p for p in playlists() if p.lower() == query.lower()), None)
        if mine:
            return play_playlist(mine)
    if not a.get("_opened"):
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
            "Lights', 'play some Drake', 'put on my workout playlist'. His own saved playlists: "
            + (", ".join(playlists()) or "none") + " (kind playlist). Music with nothing named: an "
            "empty query, and it says what to ask. 'On YouTube': use open_website "
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
