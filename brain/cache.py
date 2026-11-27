"""Answers Jarvis has already worked out, reused instead of asking a model again.

Two kinds, both in memory/answer_cache.json:

  jobs     The output of a one-off generation job (llm.complete with cache=True):
           a whiteboard diagram for "LED wiring to an Arduino Uno", a 3D model,
           pointer guide steps. Keyed by the job's instructions plus the request's
           words in any order, so "wire an LED to an Arduino" and "Arduino LED
           wiring" share one entry. Kept 30 days.
  answers  Spoken replies to standalone questions that used no tool and don't
           depend on the time, his data or the conversation ("how many ounces in
           a pound", "what's the capital of Peru"). Kept 7 days.

Anything about now (weather, time, news, prices, calendar, email, the screen),
about him ("my", "I"), about earlier talk ("it", "that", "again") or meant to be
different each time (jokes, stories, ideas) is never cached."""
import hashlib
import json
import os
import re
import threading
import time

import config

JOB_DAYS = 30
ANSWER_DAYS = 7
MAX_ENTRIES = 400
_lock = threading.Lock()
_data = None

_STOP = set("a an the and or for of to in on at by with is are be it its this that what whats what's how do does "
            "can could would will you your me please jarvis sir hey ok okay so just tell show give".split())

# Never a cached answer: changes with time, is about him or his PC, needs the earlier talk, or should vary.
_FRESH = re.compile(
    r"\b(?:now|today|tonight|tomorrow|yesterday|this (?:week|month|year|morning|afternoon|evening)|current(?:ly)?|"
    r"latest|recent|news|weather|forecast|temperature|rain|snow|time|date|day|price|stock|score|won|win|game|"
    r"traffic|calendar|schedule|meeting|email|inbox|message|remind|timer|alarm|"
    r"my|mine|me|i|i'm|im|i've|we|our|us|"
    r"it|this|that|these|those|they|them|he|she|him|her|his|there|here|again|more|another|else|other|"
    r"same|instead|also|next|previous|last|step|before|after|then|"
    r"joke|story|poem|riddle|fun fact|random|surprise|idea|ideas|suggest|recommend|pick|choose|"
    r"screen|page|article|file|folder|open|close|play|pause|set|turn|send|make|draw|write|create|save|delete|"
    r"search|look|find|check|read|remember|forget|cancel|stop|start)\b", re.I)
# A question, not a command or chit-chat.
_QUESTION = re.compile(r"^(?:what|whats|what's|who|whos|who's|where|when|which|why|how|is|are|does|do|can|"
                       r"could|define|explain|convert)\b", re.I)


def _path():
    return os.path.join(config.MEMORY_DIR, "answer_cache.json")


def _load():
    global _data
    if _data is None:
        try:
            with open(_path(), encoding="utf-8") as f:
                _data = json.load(f)
            if not isinstance(_data, dict):
                _data = {}
        except (OSError, ValueError):
            _data = {}
    return _data


def _save():
    try:
        os.makedirs(config.MEMORY_DIR, exist_ok=True)
        items = sorted(_data.items(), key=lambda kv: kv[1].get("used", 0))[-MAX_ENTRIES:]
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(items), f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path())
    except OSError:
        pass


def words(text: str) -> str:
    """The request's meaningful words, in a fixed order: the same ask worded differently matches."""
    ws = re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", ""))
    out = set()
    for w in ws:
        if w in _STOP or len(w) < 2:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            w = w[:-1]                                  # LEDs = LED, wires = wire
        out.add(w)
    return " ".join(sorted(out))


def _key(kind: str, scope: str, text: str) -> str:
    body = words(text)
    if not body:
        return ""
    h = hashlib.sha1(scope.encode("utf-8")).hexdigest()[:10]
    return f"{kind}:{h}:{body}"


def _get(key: str, days: float):
    if not key or not getattr(config, "ANSWER_CACHE", True):
        return None
    with _lock:
        entry = _load().get(key)
        if not entry or time.time() - entry.get("at", 0) > days * 86400:
            return None
        entry["used"] = time.time()
        entry["hits"] = entry.get("hits", 0) + 1
        return entry.get("value")


def _put(key: str, value: str):
    if not key or not value or not getattr(config, "ANSWER_CACHE", True):
        return
    with _lock:
        now = time.time()
        _load()[key] = {"value": value, "at": now, "used": now, "hits": 0}
        _save()


def forget(key_or_kind: str):
    """Drop cached entries: one key, or a whole kind ("job", "answer", or "all")."""
    if not key_or_kind:
        return
    with _lock:
        d = _load()
        for k in [k for k in d if key_or_kind == "all" or k == key_or_kind or k.startswith(key_or_kind + ":")]:
            del d[k]
        _save()


# ---------- generation jobs ----------
def job_key(system: str, prompt: str) -> str:
    return _key("job", system, prompt)


def get_job(system: str, prompt: str):
    return _get(_key("job", system, prompt), JOB_DAYS)


def put_job(system: str, prompt: str, text: str):
    _put(_key("job", system, prompt), text)


def reuse(system: str, request: str, make, check=None) -> str:
    """The saved answer to this job (system = the job's instructions, request = what he asked for, in his
    words) if there is one that still passes check; else make() it and save it."""
    if request:
        hit = get_job(system, request)
        if hit is not None:
            try:
                if check is not None:
                    check(hit)
                from brain import usage
                usage.saved(f"reused the saved answer for \"{request[:60]}\"")
                return hit
            except ValueError:
                pass          # the checks changed since it was saved: make a new one
    out = make()
    if request:
        put_job(system, request, out)
    return out


# ---------- spoken answers ----------
def cacheable_question(text: str) -> bool:
    t = (text or "").strip()
    return (bool(_QUESTION.match(t)) and 2 <= len(t.split()) <= 20 and not _FRESH.search(t)
            and not t.startswith("["))


def get_answer(text: str):
    if not cacheable_question(text):
        return None
    return _get(_key("answer", "", text), ANSWER_DAYS)


def put_answer(text: str, reply: str):
    if cacheable_question(text) and reply and len(reply) < 600 and "[" not in reply and reply.rstrip()[-1] in ".!" \
            and not re.search(r"\b(?:sorry|can't|cannot|couldn't|don't know|not sure|unable)\b", reply, re.I):
        _put(_key("answer", "", text), reply)
