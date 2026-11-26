"""The brain: Claude, conversation memory, and tools (see skills/)."""
import re
import threading
import time
from datetime import datetime

import anthropic

import config
from brain import auto_memory, backup, local_llm, memory, network, offline, providers, settings
import skills

# The SDK's defaults (10 minute timeout, 2 retries) let one stuck request
# freeze Jarvis for up to half an hour; seen twice in jarvis.log on 25 Nov.
# For a stream the timeout is the longest gap between chunks, not the whole reply.
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=30.0, max_retries=1)

# Whole user/assistant text pairs, oldest first. Loaded from disk so the
# conversation survives a restart.
_history = memory.load_history()
if _history:
    print(f"[memory] picked up the last conversation ({len(_history) // 2} turns)")

# End of a sentence: . ! or ? (plus closing quotes/brackets) followed by a space.
# Needing the space keeps numbers like "3.5" together.
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*\s+")
# A comma/semicolon/dash pause; used to start speaking the first reply sooner.
_CLAUSE_END = re.compile(r"(?:[,;:]|\s[-\u2013\u2014])\s+")
FIRST_CLAUSE_WORDS = 5

MAX_TOOL_ROUNDS = 4
# Room for Claude's (hidden) thinking plus a short spoken reply. With 300 the
# thinking alone could use everything up and Jarvis said nothing at all.
MAX_TOKENS = 1500
# Low effort = less thinking = faster replies; fine for voice chat.
LLM_EFFORT = getattr(config, "LLM_EFFORT", "low")
# Saved history keeps only what was said, so without this Claude sees itself
# saying "Apple Music is open" with no tool call and "corrects" itself.
_HISTORY_NOTE = (
    "\nEarlier turns are stored as plain text; any tools you used then are noted "
    "in [square brackets] at the end of your reply; [interrupted] means he cut you "
    "off there and didn't hear the rest. Never read those notes aloud, "
    "and don't apologise for or correct earlier replies unless he says something was wrong. "
    "Those notes are past actions only: if he asks for the same thing again ('max volume' "
    "twice), call the tool again. Never say you did something this turn without calling its tool."
)


def _system_prompt(about: str = "") -> str:
    """The configured prompt plus the current local date and time, so Jarvis
    can answer "what time is it?", plus everything he's been asked to remember."""
    now = datetime.now().astimezone()
    hour = now.strftime("%I").lstrip("0") or "12"
    stamp = now.strftime(f"%A %d %B %Y, {hour}:%M %p")
    prompt = f"{config.SYSTEM_PROMPT} {settings.prompt_lines()}{_HISTORY_NOTE}\nCurrent local date and time: {stamp} ({now.tzname()})."
    facts = memory.load_facts()
    # Many facts: only the ones that matter for what he just said (and the last reply).
    recent = _history[-1]["content"] if _history else ""
    facts = memory.relevant_facts(facts, f"{about} {recent}", config.FACTS_IN_PROMPT)
    if facts:
        prompt += "\nThings you know about the user:\n" + "\n".join(f"- {f}" for f in facts)
    return prompt + skills.suggestions.prompt_lines()


def _trim():
    # Trim in whole pairs before adding the new turn, so the history
    # always starts with a user message.
    keep = max(0, (config.MAX_HISTORY_TURNS - 1) * 2)
    if len(_history) > keep:
        del _history[: len(_history) - keep]


# When Claude stops working for billing/key/limit reasons, Jarvis uses the
# backup model for this long before trying Claude again.
BACKUP_MINUTES = getattr(config, "BACKUP_MINUTES", 15)
_claude_off_until = 0.0
last_ignored = False  # the last follow-up wasn't meant for Jarvis
def _use_claude() -> bool:
    return bool(config.ANTHROPIC_API_KEY) and time.monotonic() >= _claude_off_until


def _first_break(buf, said):
    """The first thing he says can end at a comma once it's a few words long,
    so his voice starts sooner; later ones wait for the full sentence."""
    m = _SENTENCE_END.search(buf)
    if said or m:
        return m
    for m in _CLAUSE_END.finditer(buf):
        if len(buf[: m.start()].split()) >= FIRST_CLAUSE_WORDS:
            return m
    return None


def _sentences(pieces, said):
    """Turns streamed text pieces into whole sentences as soon as each ends."""
    buf = ""
    for delta in pieces:
        buf += delta
        while (m := _first_break(buf, said)):
            sentence = buf[: m.end()].strip()
            buf = buf[m.end():]
            if sentence:
                said.append(sentence)
                yield sentence
    if buf.strip():
        said.append(buf.strip())
        yield buf.strip()


def _claude_turn(user_text, system, said, tools_used, exclude=(), history=None):
    # Tool calls live only in this turn's working copy; the saved history
    # keeps just what was said, so it stays simple user/assistant pairs.
    messages = (_history if history is None else history) + [{"role": "user", "content": user_text}]
    stop_reason = None
    for _ in range(MAX_TOOL_ROUNDS + 1):
        with _client.messages.stream(
            model=config.LLM_MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": LLM_EFFORT},
            system=system,
            messages=messages,
            tools=skills.anthropic_tools(exclude),
        ) as stream:
            yield from _sentences(stream.text_stream, said)
            final = stream.get_final_message()

        stop_reason = final.stop_reason
        tool_uses = [b for b in final.content if b.type == "tool_use"]
        if final.stop_reason != "tool_use" or not tool_uses:
            break
        messages.append({"role": "assistant", "content": final.content})
        results = []
        for b in tool_uses:
            out = skills.run(b.name, b.input)
            tools_used.append(f"{b.name} -> {str(out)[:80]}")
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        messages.append({"role": "user", "content": results})
    if not said:
        print(f"[brain] Claude finished without saying anything (stop: {stop_reason})")


def _openai_turn(user_text, system, said, tools_used, exclude=(), history=None, target=None):
    """The same turn on an OpenAI-style model: Groq, or OpenRouter when target is None."""
    past = list(_history if history is None else history)
    if target and target.get("short_tools"):
        # Small free token budgets: the last few turns and only the tools that look relevant.
        past = past[-2 * getattr(config, "GROQ_HISTORY_TURNS", 4):]
        keep = skills.pick_tools(user_text, exclude=exclude)
        # "Yes" to a question about a draft or a click needs the tool from the last turn.
        last = past[-1]["content"] if past and past[-1]["role"] == "assistant" else ""
        keep |= set(re.findall(r"(?:\[tools used: |; )([a-z_]+) ->", last))
        exclude = tuple(exclude) + tuple(s["name"] for s in skills.SKILLS if s["name"] not in keep)
    messages = [{"role": "system", "content": system}] + past + [{"role": "user", "content": user_text}]
    t0 = time.perf_counter()
    model = None
    for _ in range(MAX_TOOL_ROUNDS + 1):
        result = {}

        def pieces():
            for kind, value in backup.stream_round(messages, exclude, target):
                if kind == "text":
                    yield value
                else:
                    result["done"] = value
        yield from _sentences(pieces(), said)
        text, tool_calls, model = result["done"]
        if not tool_calls:
            break
        messages.append({"role": "assistant", "content": text or None, "tool_calls": tool_calls})
        for call in tool_calls:
            name = call["function"]["name"]
            out = skills.run(name, backup.parse_args(call))
            tools_used.append(f"{name} -> {str(out)[:80]}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
    who = (target or {}).get("who") or "backup model"
    print(f"[brain] {who} ({model or '?'}) answered in {time.perf_counter() - t0:.1f}s")


def _backup_turn(user_text, system, said, tools_used, exclude=(), history=None):
    """The same turn on the free OpenRouter model (OpenAI message format)."""
    yield from _openai_turn(user_text, system, said, tools_used, exclude, history)


def _already_done(asked, tools_used):
    """A brain failed after running tools: tell the next one so it doesn't repeat them."""
    if not tools_used:
        return asked
    return (f"[Already done this turn, don't repeat these tools, just tell him the result: "
            f"{'; '.join(tools_used)}]\n" + asked)


def _chain(asked, system, said, tools_used, exclude=(), history=None):
    """Answer with the cheapest brain that works (providers.order()): Groq's
    free models, then OpenRouter's, then Claude. One that fails before saying
    anything is rested and the next takes over."""
    global _claude_off_until
    errors = []
    for name in providers.order():
        if name == "groq":
            for target in providers.groq_targets():
                try:
                    yield from _openai_turn(_already_done(asked, tools_used), system, said, tools_used,
                                            exclude, history, target)
                    return
                except Exception as e:
                    if said or network.is_network_error(e):
                        raise
                    providers.rest(target["model"], e)
                    errors.append(e)
        elif name == "openrouter":
            try:
                yield from _openai_turn(_already_done(asked, tools_used), system, said, tools_used,
                                        exclude, history)
                return
            except Exception as e:
                if said or network.is_network_error(e):
                    raise
                providers.rest("openrouter", e)
                errors.append(e)
        elif name == "claude":
            if not _use_claude():
                continue
            try:
                yield from _claude_turn(_already_done(asked, tools_used), system, said, tools_used,
                                        exclude, **({"history": history} if history is not None else {}))
                return
            except Exception as e:
                # Only switch if nothing was spoken yet, so he never hears a reply twice.
                if said or not backup.claude_unavailable(e):
                    raise
                _claude_off_until = time.monotonic() + BACKUP_MINUTES * 60
                print(f"[brain] Claude unavailable ({type(e).__name__}: {str(e)[:150]}), "
                      f"resting it for {BACKUP_MINUTES} minutes")
                errors.append(e)
    if errors:
        raise errors[-1]
    raise RuntimeError("No brain is set up or available: add GROQ_API_KEY (free, console.groq.com) "
                       "or ANTHROPIC_API_KEY to the .env file.")


def complete(system: str, user: str, max_tokens: int = 400, small: bool = True, models=None) -> str:
    """A one-off text answer with no tools (fact extraction, rewriting text),
    from the cheapest brain that works. Raises if none does.
    models: Groq models to try first (e.g. a bigger one for drawing diagrams)."""
    if not network.online():
        raise RuntimeError("offline: no internet for the cloud models")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    errors = []
    for name in providers.order():
        targets = []
        if name == "groq":
            targets = [dict(t, tools=False, max_tokens=max_tokens) for t in providers.groq_targets(small=small, models=models)]
        elif name == "openrouter":
            targets = [dict(backup.openrouter_target(), tools=False, max_tokens=max_tokens)]
        for target in targets:
            try:
                text = "".join(v for k, v in backup.stream_round(messages, (), target) if k == "text")
                if text.strip():
                    return text.strip()
            except Exception as e:
                providers.rest(target["model"] if name == "groq" else "openrouter", e)
                errors.append(e)
        if name == "claude" and _use_claude():
            msg = _client.messages.create(model=config.LLM_MODEL, max_tokens=max_tokens, system=system,
                                          messages=[{"role": "user", "content": user}])
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if errors:
        raise errors[-1]
    raise RuntimeError("No brain available")


def _offline_turn(user_text, asked, said, tools_used, exclude=(), followup=False):
    """No internet: simple commands are done right here (brain/offline.py),
    the rest goes to the local Ollama model with only the offline tools."""
    if not followup:
        found = offline.quick(user_text)
        if found:
            reply, tool = found
            if tool:
                tools_used.append(f"{tool} -> {reply[:80]}")
            print(f"[offline] handled without a model: {user_text}")
            said.append(reply)
            yield reply
            return
    if offline.model_ready():
        try:
            yield from _openai_turn(asked, offline.system_prompt(), said, tools_used,
                                    offline.exclude(exclude), target=offline.target())
            return
        except Exception as e:
            if said:
                raise
            offline.model_failed(e)
    reply = IGNORE if followup else offline.BASICS
    said.append(reply)
    yield reply


class _HandOff(Exception):
    """The local model passed the question on to Claude."""


def _local_turn(user_text, said):
    """An easy question answered by the local Ollama model (brain/local_llm.py).
    Raises _HandOff before saying anything if it should go to Claude instead."""
    messages = ([{"role": "system", "content": local_llm.SYSTEM}] + _history[-4:]
                + [{"role": "user", "content": user_text}])
    t0 = time.perf_counter()

    def pieces():
        head, checked = "", False
        for kind, value in backup.stream_round(messages, target=local_llm.target()):
            if kind != "text":
                continue
            if checked:
                yield value
                continue
            head += value
            if len(head) >= len(local_llm.HANDOFF) + 4:
                if local_llm.handed_off(head):
                    raise _HandOff()
                checked = True
                yield head
        if not checked:
            if local_llm.handed_off(head):
                raise _HandOff()
            yield head
    yield from _sentences(pieces(), said)
    print(f"[brain] local model {config.LOCAL_MODEL} answered in {time.perf_counter() - t0:.1f}s")


# Added to what was heard when Jarvis keeps listening after a reply (no wake
# word), so he stays quiet when it's someone else talking in the room.
FOLLOWUP_NOTE = (
    "[Heard without the wake word, a few seconds after your last reply. It may be "
    "someone else in the room, or him talking to someone else. Answer only if it is "
    "clearly meant for you: a question or request to you, or a direct reply to what "
    "you just said. Otherwise answer with exactly [ignore] and nothing else.]\n"
)
IGNORE = "[ignore]"


# One conversation at a time: the mic and the Telegram bot share the history.
_turn_lock = threading.Lock()

# Barge-in: the voice side reports how much of the reply was actually heard,
# so the history doesn't claim he said sentences that were cut (idea from
# GLaDOS, github.com/dnhkng/GLaDOS, MIT). The turn may still be finishing
# when that arrives, so it's either applied now or kept for the turn's end.
_clip_lock = threading.Lock()
_turn_running = False
_pending_clip = None
INTERRUPTED = "[interrupted]"


def _clipped(spoken: str) -> str:
    return f"{spoken} {INTERRUPTED}".strip()


def clip_last_reply(spoken: str):
    """Replace the last reply in the history with only the part he heard."""
    global _pending_clip
    with _clip_lock:
        if _turn_running:
            _pending_clip = spoken
            return
        if _history and _history[-1]["role"] == "assistant":
            tools = re.search(r" \[tools used: .*\]$", _history[-1]["content"])
            _history[-1]["content"] = _clipped(spoken) + (tools.group(0) if tools else "")
            memory.save_history(_history)


def think_stream(user_text: str, followup: bool = False, note: str = "", exclude_tools=()):
    """See _think_stream. Waits if another turn (say, from his phone) is running."""
    with _turn_lock:
        yield from _think_stream(user_text, followup, note, exclude_tools)


def _think_stream(user_text: str, followup: bool = False, note: str = "", exclude_tools=()):
    """Yields the reply one sentence at a time while Claude is still writing,
    so Jarvis can start speaking the first sentence straight away.
    If Claude uses a tool (remember/forget), runs it and carries on.
    If Claude is out of credits (or the key or rate limit fails), the free
    backup model on OpenRouter answers instead."""
    global _claude_off_until, last_ignored, _turn_running, _pending_clip
    last_ignored = False
    with _clip_lock:
        _turn_running, _pending_clip = True, None
    skills.new_turn()
    _trim()
    asked = (FOLLOWUP_NOTE if followup else "") + note + user_text
    # Overheard chatter must never be able to switch him off.
    exclude = tuple(exclude_tools) + (("shut_down",) if followup else ())
    # Build the system prompt once per turn: Claude's thinking blocks are tied
    # to it, so if the clock ticked over to a new minute between tool rounds the
    # API rejected the second round ("Invalid signature in thinking block").
    system = _system_prompt(user_text)
    said, tools_used = [], []

    def turn():
        global _claude_off_until
        if not network.online():
            yield from _offline_turn(user_text, asked, said, tools_used, exclude, followup)
            return
        if local_llm.should_use(user_text, followup, note):
            try:
                yield from _local_turn(user_text, said)
                return
            except _HandOff:
                print("[brain] local model passed it on")
            except Exception as e:
                if said:
                    raise
                local_llm.failed(e)
        try:
            yield from _chain(asked, system, said, tools_used, exclude)
        except Exception as e:
            # The wifi dropped mid-way: do what can be done offline instead.
            if said or not network.is_network_error(e):
                raise
            network.mark_offline()
            yield from _offline_turn(user_text, asked, said, tools_used, exclude, followup)

    gen = turn()
    try:
        for sentence in gen:
            if followup and len(said) == 1 and sentence.lower().startswith(IGNORE[:-1]):
                last_ignored = True
                print(f"[brain] ignored (not meant for Jarvis): {user_text}")
                break
            yield sentence
    finally:
        gen.close()
        with _clip_lock:
            reply = " ".join(said) if _pending_clip is None else _clipped(_pending_clip)
            _turn_running, _pending_clip = False, None
        if reply and not last_ignored:
            spoken_reply = reply
            if tools_used:
                reply += " [tools used: " + "; ".join(tools_used) + "]"
            _history.append({"role": "user", "content": user_text})
            _history.append({"role": "assistant", "content": reply})
            memory.save_history(_history)
            auto_memory.run_in_background(user_text, spoken_reply, tools_used)


def run_job(prompt: str, exclude_tools=()) -> str:
    """A one-off turn for a scheduled job: no conversation history, nothing
    saved, and only the tools not in exclude_tools. Returns the whole reply."""
    system = _system_prompt(prompt) + (
        "\nThis is a scheduled job running in the background, not a live conversation: "
        "do it and report the result briefly, as it will be read aloud or sent to his phone.")
    said, used = [], []
    exclude = tuple(exclude_tools) + ("shut_down",)
    try:
        for _ in _chain(prompt, system, said, used, exclude, history=[]):
            pass
    except Exception as e:
        if not said:
            raise
        print(f"[jobs] the brain failed part-way ({e}); keeping what came back")
    return " ".join(said).strip()


def think(user_text: str) -> str:
    """Whole reply at once (handy for testing)."""
    return " ".join(think_stream(user_text))


def reset():
    """Start a fresh conversation (saved facts are kept)."""
    _history.clear()
    memory.save_history(_history)
