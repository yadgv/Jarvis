"""Jarvis talks to Jarvis: a second AI plays you, with a goal, and has a real
back-and-forth with him. A third call grades each conversation.

    python3.13 talk_tests.py                 every scenario (free models only, never Claude)
    python3.13 talk_tests.py --only slides --delay 8

As in run_tests.py, every tool is a dry run (written down, not done). The
scenarios are in testbench/scenarios.py; the report (whole transcripts with
grades) goes to testbench/reports/.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import run_tests  # sets up config and the dry run, same as the question bench
from run_tests import fakes, llm, main, sight, skills, documents  # noqa: F401
from testbench.scenarios import JUDGE, PERSONA, SCENARIOS

HERE = os.path.dirname(os.path.abspath(__file__))
DONE = re.compile(r"<\s*done\s*>", re.I)


def _ask(system, user, delay, max_tokens=120):
    """A free-model answer, waiting once for rate limits."""
    for attempt in (1, 2):
        try:
            return llm.complete(system, user, max_tokens=max_tokens)
        except Exception as e:
            if attempt == 2:
                raise
            wait = run_tests.rest_wait(delay)
            print(f"    (free models busy: {str(e)[:80]}; waiting {wait:.0f}s)")
            time.sleep(wait)


def transcript_text(lines):
    out = []
    for who, text, tools in lines:
        out.append(f"{who}: {text}" + (f"   [tools used: {', '.join(tools)}]" if tools else ""))
    return "\n".join(out)


def next_line(scenario, lines, delay):
    """What the simulated Ziad says next ('' when he's finished)."""
    if not lines:
        return scenario["opener"]
    prompt = ("The conversation so far (you are Ziad):\n" + transcript_text(lines) +
              "\n\nWhat do you say next? Only your words, or <done> if you already said goodbye.")
    said = _ask(PERSONA.format(goal=scenario["goal"]), prompt, delay)
    said = re.sub(r"^\s*(?:ziad|you)\s*:\s*", "", said.strip().strip('"'), flags=re.I).splitlines()[0].strip()
    return "" if DONE.search(said) else said


def judge(scenario, lines, delay):
    raw = _ask(JUDGE.format(goal=scenario["goal"]), transcript_text(lines), delay, max_tokens=300)
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except ValueError:
        out = {}
    if not out:
        return {"goal_done": None, "score": None, "problems": [f"judge gave no grade: {raw[:120]}"]}
    return {"goal_done": bool(out.get("goal_done")), "score": out.get("score"),
            "problems": [str(p) for p in out.get("problems") or []][:4]}


def run_scenario(scenario, rec, delay):
    run_tests.setup_case(scenario, rec)
    llm._history.clear()
    lines, used, ended = [], [], ""
    asked = False
    for turn in range(scenario.get("turns", 5)):
        try:
            said = next_line(scenario, lines, delay)
        except Exception as e:
            if not lines:
                raise                      # nothing ran: the caller marks it skipped
            ended = f"stopped early: no free models ({str(e)[:100]})"
            break
        if not said:
            ended = "he finished"
            break
        print(f"  Ziad:   {said}")
        if turn:
            addressed, rest = main.strip_name(said)
            action = main.followup_action(main.normalize(rest if addressed else said), asked, addressed)
            if action == "close":
                lines.append(("Ziad", said, []))
                ended = "conversation closed (goodbye heard)"
                break
        n = len(rec.calls)
        start = time.perf_counter()
        try:
            reply = " ".join(llm.think_stream(said, followup=turn > 0)).strip()
        except Exception as e:
            reply = f"(error: {type(e).__name__}: {str(e)[:150]})"
        took = time.perf_counter() - start
        tools = [c[0] for c in rec.calls[n:]]
        used += tools
        print(f"  Jarvis: {reply[:200]}  ({took:.1f}s{', ' + ', '.join(tools) if tools else ''})")
        lines += [("Ziad", said, []), ("Jarvis", reply or "(said nothing)", tools)]
        asked = reply.rstrip().endswith("?")
        time.sleep(delay)
    else:
        ended = "ran out of turns"
    try:
        grade = judge(scenario, lines, delay) if lines else {"goal_done": False, "score": 1, "problems": ["no talk"]}
    except Exception as e:
        grade = {"goal_done": None, "score": None, "problems": [f"not graded: no free models ({str(e)[:100]})"]}
    missing = [t for t in scenario.get("expect", []) if t not in used]
    bad = [t for t in scenario.get("avoid", []) if t in used]
    problems = ([f"never used {', '.join(missing)}"] if missing else []) + \
               ([f"used {', '.join(bad)} (must not)"] if bad else []) + \
               [p for p in grade["problems"]]
    errors = [text for who, text, _ in lines if who == "Jarvis" and text.startswith("(error")]
    ok = not missing and not bad and not errors and grade["goal_done"] is not False and (grade["score"] or 0) >= 3
    if ok is False and not (missing or bad or errors) and grade["score"] is None and (
            "stopped early" in ended or any(p.startswith("not graded") for p in grade["problems"])):
        ok = None                          # cut short by the free models, not by Jarvis: not a fail
    out = "stopped early" in ended or any(p.startswith("not graded: no free models") for p in grade["problems"])
    return {"id": scenario["id"], "goal": scenario["goal"], "ok": ok, "score": grade["score"], "out_of_models": out,
            "goal_done": grade["goal_done"], "ended": ended, "tools": used, "problems": problems,
            "transcript": [{"who": w, "said": t, "tools": tl} for w, t, tl in lines]}


def skipped(scenario, why):
    return {"id": scenario["id"], "goal": scenario["goal"], "ok": None, "score": None, "goal_done": None,
            "ended": why, "tools": [], "problems": [why], "transcript": []}


def report(results, folder=None):
    ran = [r for r in results if r["ok"] is not None]
    passed = sum(bool(r["ok"]) for r in ran)
    skips = len(results) - len(ran)
    scores = [r["score"] for r in results if isinstance(r["score"], (int, float))]
    avg = f"{sum(scores) / len(scores):.1f}/5" if scores else "n/a"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    folder = folder or os.path.join(HERE, "testbench", "reports")
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, f"{stamp}_talk")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"when": stamp, "passed": passed, "total": len(ran), "skipped": skips, "average": avg,
                   "talks": results},
                  f, indent=1)
    skip_note = f", {skips} skipped (no free models left)" if skips else ""
    lines = [f"# Jarvis talks to Jarvis, {stamp}", "",
             f"**Passed {passed}/{len(ran)}{skip_note}, average grade {avg}**", ""]
    for r in results:
        mark = "⏭️" if r["ok"] is None else "✅" if r["ok"] else "❌"
        lines += [f"## {mark} {r['id']} (grade {r['score']}, {r['ended']})", "",
                  f"Goal: {r['goal']}", ""]
        lines += [f"- {p}" for p in r["problems"]] + ([""] if r["problems"] else [])
        for t in r["transcript"]:
            lines.append(f"> **{t['who']}:** {t['said']}" + (f"  `{', '.join(t['tools'])}`" if t["tools"] else ""))
            lines.append(">")
        lines.append("")
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nPassed {passed}/{len(ran)}{skip_note}, average grade {avg}. Report: {base}.md")
    return passed, len(ran)


def run(scenarios, delay):
    rec = fakes.Recorder()
    real = (skills.run, sight.read, documents.last)
    skills.run = rec
    results = []
    out_of_models = ""
    try:
        for s in scenarios:
            if out_of_models:
                results.append(skipped(s, out_of_models))
                continue
            print(f"\n== {s['id']}: {s['goal']}")
            try:
                r = run_scenario(s, rec, delay)
                results.append(r)
                if r.pop("out_of_models", ""):
                    out_of_models = "skipped: no free models left (they ran out during an earlier talk)"
            except KeyboardInterrupt:
                print("\nStopped: writing the report of what ran so far.")
                break
            except Exception as e:
                # Every free model is resting (rate limits, used-up daily quotas): don't crash, say so.
                out_of_models = f"skipped: no free models ({type(e).__name__}: {str(e)[:160]})"
                print(f"  {out_of_models}")
                results.append(skipped(s, out_of_models))
    finally:
        skills.run, sight.read, documents.last = real
        sight.last.update(title="", url="", text="", at=0.0)
    return results


def main_cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="run scenarios whose id contains this")
    ap.add_argument("--delay", type=float, default=5.0, help="seconds between turns (free-model rate limits)")
    a = ap.parse_args(argv)
    if not run_tests.go_live():
        print("No free AI model is set up (GROQ_API_KEY, GEMINI_API_KEY...): talk tests need one.")
        return 2
    scenarios = [s for s in SCENARIOS if not a.only or a.only.lower() in s["id"]]
    passed, total = report(run(scenarios, a.delay))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main_cli())
