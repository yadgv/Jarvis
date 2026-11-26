"""Ask Jarvis a list of real questions and see how he does.

    python3.13 run_tests.py              live: the free AI models answer (never Claude)
    python3.13 run_tests.py --offline    no AI: only the routing he decides himself
    python3.13 run_tests.py --only brief --delay 8

Nothing really happens on the PC: every tool is a dry run (written down, not
done). The conversations are in testbench/cases.py. A report goes to
testbench/reports/ (Markdown to read, JSON to compare runs).
"""
import argparse
import json
import os
import re
import sys
import time
import types
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _stub_missing():
    """Let it run on a PC without the audio libraries (and in the cloud)."""
    for name, attrs in {"sounddevice": {"play": lambda *a, **k: None, "wait": lambda: None, "InputStream": object},
                        "faster_whisper": {"WhisperModel": lambda *a, **k: None},
                        "anthropic": {"Anthropic": lambda **k: None}}.items():
        try:
            __import__(name)
        except Exception:
            mod = types.ModuleType(name)
            for k, v in attrs.items():
                setattr(mod, k, v)
            sys.modules[name] = mod


_stub_missing()
import config  # noqa: E402

config.MODE = "enter"            # no wake-word model
config.AUTO_MEMORY = False       # nothing he says in a test is saved as a fact
config.BACKGROUND_TASKS = False
config.LOG_FILE = ""
import main  # noqa: E402
import skills  # noqa: E402
from skills import documents, sight, workspace  # noqa: E402
from brain import llm, memory, providers  # noqa: E402
from testbench import fakes  # noqa: E402
from testbench.cases import CASES  # noqa: E402


def as_list(v):
    return [] if v is None else ([v] if isinstance(v, str) else list(v))


def conversation_checks(turn):
    """close / addressed: decided by main.py, the same in both modes."""
    problems = []
    addressed, rest = main.strip_name(turn["say"])
    if "addressed" in turn and addressed != turn["addressed"]:
        problems.append(f"name: addressed={addressed}, expected {turn['addressed']}")
    if "close" in turn:
        said = main.normalize(rest if addressed else turn["say"])
        action = main.followup_action(said, turn.get("answering", False), addressed)
        if (action == "close") != turn["close"]:
            problems.append(f"conversation: '{action}', expected {'close' if turn['close'] else 'carry on'}")
    return problems, rest if addressed else turn["say"]


def setup_case(case, rec):
    screen = fakes.ARTICLES.get(case.get("screen")) if case.get("screen") else None
    rec.screen = screen or {}
    sight.read = fakes.fake_read(screen)
    sight.last.update(title="", url="", text="", at=0.0)
    with workspace._lock:
        workspace._ws["doc"] = ""
    documents.last = (lambda: dict(fakes.LAST_DOC)) if case.get("last_doc") else (lambda: None)


def check_offline(turn, request, prev_tools):
    """What can be checked without a model: tools run directly, tools hidden from
    the model, and whether the right tool is among those the model is shown."""
    plan = skills.route(request)
    direct = [n for n, _ in plan["direct"]]
    shown = skills.pick_tools(request, limit=10, exclude=tuple(plan["exclude"])) | set(prev_tools)
    if not skills._VISUAL.search(request):
        shown.discard("look_at_screen")
    want, problems = as_list(turn.get("tool")), []
    if want == ["none"]:
        if direct:
            problems.append(f"ran {direct} but no tool was wanted")
    elif want:
        if direct and not set(direct) & set(want):
            problems.append(f"ran {direct} directly, wanted {want}")
        elif not direct and not (shown & set(want)) and "none" not in want:
            problems.append(f"{' / '.join(want)} not offered to the model")
    for bad in as_list(turn.get("not")) + as_list(turn.get("hide")):
        if bad in direct:
            problems.append(f"{bad} was run (must not be)")
    for bad in as_list(turn.get("hide")):
        if bad in shown:
            problems.append(f"{bad} was offered to the model (must be hidden)")
    return {"tools": direct, "offered": sorted(shown), "spoken": "", "problems": problems}


def rest_wait(delay, most=120):
    """How long until a free model that's resting (after a rate limit) can be tried again."""
    now = time.monotonic()
    soon = [t - now for t in providers._resting.values() if t > now]
    return max(delay * 4, min(min(soon) + 1, most) if soon else 0)


BRAIN_ERRORS = []   # (model, error) for every free model that failed, so the report says who and why


def _watch_rests():
    real = providers.rest

    def rest(key, e):
        BRAIN_ERRORS.append(f"{key}: {str(e)[:160]}")
        return real(key, e)
    providers.rest = rest
    return real


def check_live(turn, request, rec, followup, delay):
    want = as_list(turn.get("tool"))
    BRAIN_ERRORS.clear()
    for attempt in (1, 2):
        start, n = time.perf_counter(), len(rec.calls)
        spoken, error = [], ""
        try:
            for sentence in llm.think_stream(request, followup=followup):
                spoken.append(sentence)
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)[:200]}"
        took = time.perf_counter() - start
        if not error or spoken or attempt == 2:
            break
        wait = rest_wait(delay)
        print(f"    brain failed ({error}); waiting {wait:.0f}s for the free models and trying once more")
        time.sleep(wait)
    calls = rec.calls[n:]
    used = [c[0] for c in calls]
    text = " ".join(spoken).strip()
    problems = []
    if error and not text:
        problems.append(f"no answer: {error}")
    if want == ["none"] and used:
        problems.append(f"used {used}, wanted no tool")
    elif want and want != ["none"] and not set(used) & set(want) and not ("none" in want and not used):
        problems.append(f"used {used or 'no tool'}, wanted {' / '.join(w for w in want if w != 'none')}")
    for bad in as_list(turn.get("not")) + as_list(turn.get("hide")):
        if bad in used:
            problems.append(f"used {bad} (must not)")
    if turn.get("says_not") and re.search(turn["says_not"], text):
        problems.append(f"said something it shouldn't (matches {turn['says_not']!r})")
    if not text and not error:
        problems.append("said nothing")
    if problems and BRAIN_ERRORS:
        problems.append("models that failed: " + " | ".join(dict.fromkeys(BRAIN_ERRORS)))
    return {"tools": used, "args": [c[1] for c in calls], "spoken": text, "seconds": round(took, 1),
            "problems": problems, "brain_errors": list(BRAIN_ERRORS)}


def go_live():
    """Free models only: Claude is taken out of the order and can't be asked for."""
    config.BRAIN_ORDER = [n for n in config.BRAIN_ORDER if n != "claude"]
    llm._use_claude = lambda: False
    memory.save_history = lambda *a, **k: None   # his real conversation history is left alone
    return bool(providers.order())


def run(cases, live, delay):
    rec = fakes.Recorder()
    real = (skills.run, sight.read, documents.last)
    real_rest = _watch_rests()
    skills.run = rec
    results = []
    try:
        for case in cases:
            print(f"\n== {case['id']}")
            setup_case(case, rec)
            llm._history.clear()
            prev_tools = set()
            for i, turn in enumerate(case["turns"]):
                problems, request = conversation_checks(turn)
                needs_brain = "tool" in turn or "says_not" in turn
                row = {"case": case["id"], "turn": i + 1, "say": turn["say"], "tools": [], "spoken": "",
                       "problems": []}
                if needs_brain:
                    if live:
                        row.update(check_live(turn, request, rec, followup=i > 0, delay=delay))
                        time.sleep(delay)
                    else:
                        row.update(check_offline(turn, request, prev_tools))
                        if {"read_screen", "brief_document"} & set(as_list(turn.get("tool"))):
                            sight.read()   # what the real tool would have done: the screen was read
                    prev_tools |= set(as_list(turn.get("tool"))) - {"none"}
                row["problems"] = problems + row["problems"]
                row["ok"] = not row["problems"]
                results.append(row)
                print(f"  {'PASS' if row['ok'] else 'FAIL'}  {turn['say']}")
                if row.get("spoken"):
                    print(f"        Jarvis: {row['spoken'][:160]}")
                for p in row["problems"]:
                    print(f"        - {p}")
    finally:
        skills.run, sight.read, documents.last = real
        providers.rest = real_rest
        sight.last.update(title="", url="", text="", at=0.0)
    return results


def report(results, live, folder=None):
    passed = sum(r["ok"] for r in results)
    rate = f"{passed}/{len(results)} ({100 * passed // max(1, len(results))}%)"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    folder = folder or os.path.join(HERE, "testbench", "reports")
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, f"{stamp}_{'live' if live else 'offline'}")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"when": stamp, "live": live, "passed": passed, "total": len(results), "turns": results},
                  f, indent=1)
    lines = [f"# Jarvis test run {stamp} ({'live, free models' if live else 'offline routing'})", "",
             f"**Passed {rate}**", ""]
    fails = [r for r in results if not r["ok"]]
    if fails:
        lines += ["## Failures", ""]
        for r in fails:
            lines.append(f"- **{r['case']}** turn {r['turn']}: \"{r['say']}\"")
            lines += [f"  - {p}" for p in r["problems"]]
            if r.get("spoken"):
                lines.append(f"  - Jarvis said: \"{r['spoken'][:300]}\"")
        lines.append("")
    lines += ["## Every turn", "", "| | case | he said | tools | Jarvis said | s |", "|---|---|---|---|---|---|"]
    for r in results:
        said = (r.get("spoken") or "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(f"| {'✅' if r['ok'] else '❌'} | {r['case']} | {r['say']} | {', '.join(r['tools'])} | "
                     f"{said} | {r.get('seconds', '')} |")
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nPassed {rate}. Report: {base}.md")
    return passed, len(results)


def main_cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="no AI calls: check routing only")
    ap.add_argument("--only", help="run cases whose id contains this (e.g. brief, bye)")
    ap.add_argument("--limit", type=int, help="run at most this many cases")
    ap.add_argument("--delay", type=float, default=5.0, help="seconds between questions (free-model rate limits)")
    a = ap.parse_args(argv)
    cases = [c for c in CASES if not a.only or a.only.lower() in c["id"]][:a.limit or None]
    live = not a.offline and go_live()
    if live:
        print(f"Free models to use: {', '.join(providers.order())}")
    if not a.offline and not live:
        print("No free AI model is set up (GROQ_API_KEY, GEMINI_API_KEY...), so this is an offline run.")
    results = run(cases, live, a.delay)
    passed, total = report(results, live)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main_cli())
