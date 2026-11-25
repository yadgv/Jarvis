"""Standing jobs and watchers: "every weekday at 8, tell me the weather and my
first meeting", "every Monday at 9, sum up my unread email", "check every 15
minutes and tell me when Mom emails".

Idea from GAIA's workflows (github.com/theexperiencecompany/gaia). Each job is
a prompt Jarvis runs on a schedule in the background (no conversation history,
read-only tools only). A watcher only speaks up when the answer is new.
Saved in memory/jobs.json, so they survive a restart."""
import hashlib
import threading
import time
import uuid
from datetime import datetime, timedelta

from brain import memory
from skills import timers

FILE = "jobs.json"
CHECK_EVERY = 20  # seconds
MIN_EVERY_MINUTES = 5
NOTHING = "[nothing]"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# Jobs may only look things up, never act (no sending, buying, clicking or switching).
SAFE_TOOLS = {
    "daily_briefing", "get_weather", "get_news", "web_search", "whats_the_buzz",
    "get_calendar_events", "check_email", "stock_price", "list_reminders", "list_timers",
    "claude_code_status",
}
_lock = threading.Lock()
_started = False
_running = set()


def _load():
    return memory._read(FILE, [])


def _save(items):
    memory._write(FILE, items)


def _days(spec):
    spec = (spec or "every day").lower()
    if spec in ("every day", "daily", "everyday", ""):
        return DAYS
    if spec == "weekdays":
        return DAYS[:5]
    if spec == "weekends":
        return DAYS[5:]
    found = [d for d in DAYS if d in spec]
    return found or DAYS


def next_run(job, after: datetime) -> datetime:
    if job.get("every_minutes"):
        return after + timedelta(minutes=job["every_minutes"])
    hour, minute = map(int, job["time"].split(":"))
    day = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day <= after:
        day += timedelta(days=1)
    for _ in range(8):
        if DAYS[day.weekday()] in job["days"]:
            return day
        day += timedelta(days=1)
    return day


def schedule_job(a):
    prompt = (a.get("task") or "").strip()
    if not prompt:
        return "What should the job do?"
    job = {"id": uuid.uuid4().hex[:6], "task": prompt, "deliver": a.get("deliver") or "speak",
           "watch": bool(a.get("only_when_new")), "last": ""}
    if a.get("every_minutes"):
        job["every_minutes"] = max(MIN_EVERY_MINUTES, int(a["every_minutes"]))
    else:
        t = (a.get("time") or "").strip()
        try:
            datetime.strptime(t, "%H:%M")
        except ValueError:
            return "Give time as HH:MM (24-hour), or every_minutes."
        job["time"], job["days"] = t, _days(a.get("days"))
    job["next"] = next_run(job, datetime.now()).isoformat(timespec="minutes")
    with _lock:
        items = _load()
        items.append(job)
        _save(items)
    return f"Job {job['id']} saved: {describe(job)}. First run {job['next'].replace('T', ' ')}."


def describe(job):
    if job.get("every_minutes"):
        when = f"every {job['every_minutes']} minutes"
    else:
        days = "every day" if len(job["days"]) == 7 else ("weekdays" if job["days"] == DAYS[:5] else ", ".join(job["days"]))
        when = f"{days} at {job['time']}"
    kind = "watch" if job.get("watch") else "job"
    return f"{kind} {when}: {job['task']} (to {job['deliver']})"


def list_jobs(a):
    items = _load()
    return "\n".join(f"{j['id']}: {describe(j)}" for j in items) if items else "No standing jobs."


def cancel_job(a):
    key = (a.get("id_or_words") or "").strip().lower()
    with _lock:
        items = _load()
        keep = [j for j in items if not (j["id"] == key or (key and key in j["task"].lower()))]
        _save(keep)
    gone = len(items) - len(keep)
    return f"Cancelled {gone} job(s)." if gone else "No job matched."


def _prompt(job):
    if job.get("watch"):
        return (f"{job['task']}\nThis is a watch that runs repeatedly. If there is nothing new or the "
                f"condition isn't met, reply with exactly {NOTHING} and nothing else. Otherwise report "
                f"what's new in one or two sentences.")
    return job["task"]


def _deliver(job, text):
    sent = False
    if job["deliver"] in ("phone", "both"):
        try:
            import telegram_bot
            sent = telegram_bot.notify(text)
        except Exception as e:
            print(f"[jobs] couldn't send to Telegram: {e}")
    if job["deliver"] in ("speak", "both") or not sent:
        timers.announce(text)


def run_one(job):
    from brain import llm
    import skills
    exclude = [s["name"] for s in skills.SKILLS if s["name"] not in SAFE_TOOLS]
    try:
        reply = llm.run_job(_prompt(job), exclude)
    except Exception as e:
        print(f"[jobs] {job['id']} failed: {e}")
        return
    finally:
        _running.discard(job["id"])
    print(f"[jobs] {job['id']}: {reply[:200]}")
    if not reply or reply.strip().lower().startswith(NOTHING[:-1]):
        return
    if job.get("watch"):
        digest = hashlib.sha1(reply.encode()).hexdigest()
        with _lock:
            items = _load()
            for j in items:
                if j["id"] == job["id"]:
                    if j.get("last") == digest:
                        return  # same news as last time
                    j["last"] = digest
            _save(items)
    _deliver(job, reply)


def _tick(now=None):
    now = now or datetime.now()
    due = []
    with _lock:
        items = _load()
        for j in items:
            if datetime.fromisoformat(j["next"]) <= now and j["id"] not in _running:
                # A job missed while Jarvis was off runs once, then carries on as normal.
                j["next"] = next_run(j, now).isoformat(timespec="minutes")
                _running.add(j["id"])
                due.append(dict(j))
        if due:
            _save(items)
    for j in due:
        threading.Thread(target=run_one, args=(j,), daemon=True).start()
    return due


def _loop():
    while True:
        try:
            _tick()
        except Exception as e:
            print(f"[jobs] {e}")
        time.sleep(CHECK_EVERY)


def start():
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_loop, daemon=True, name="jobs").start()


SKILLS = [
    {
        "name": "schedule_job",
        "description": (
            "Set up a standing job that runs on a schedule in the background: a daily/weekly report "
            "('every weekday at 8 tell me the weather and my first meeting') or a watch that only speaks "
            "up when something new happens ('check every 15 minutes and tell me when Mom emails': set "
            "only_when_new). Jobs can only look things up (weather, news, search, calendar, email, stocks, "
            "the buzz), never act. For a one-time nudge use set_reminder instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "what to do each time, as an instruction to yourself"},
                "time": {"type": "string", "description": "HH:MM, 24-hour, for daily/weekly jobs"},
                "days": {"type": "string", "description": "'every day', 'weekdays', 'weekends' or e.g. 'mon, thu'"},
                "every_minutes": {"type": "integer", "description": "for watches: how often to check (min 5)"},
                "only_when_new": {"type": "boolean", "description": "a watch: stay quiet unless there's something new"},
                "deliver": {"type": "string", "enum": ["speak", "phone", "both"],
                            "description": "say it aloud, send to his phone (Telegram), or both"},
            },
            "required": ["task"],
        },
        "run": schedule_job,
    },
    {
        "name": "list_jobs",
        "description": "List his standing jobs and watches.",
        "parameters": {"type": "object", "properties": {}},
        "run": list_jobs,
    },
    {
        "name": "cancel_job",
        "description": "Cancel a standing job or watch by its id or words from its task.",
        "parameters": {"type": "object", "properties": {"id_or_words": {"type": "string"}},
                       "required": ["id_or_words"]},
        "run": cancel_job,
    },
]
