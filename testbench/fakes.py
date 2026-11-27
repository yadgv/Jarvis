"""Stand-ins for the real world during a test run: no app opens, no file moves,
nothing is sent to his phone. Every tool call is written down and answered
with a believable result, so the brain carries on as if it worked."""
import time

ARTICLES = {
    "cbc": {
        "title": "Major data breach exposes millions of Canadians' records - CBC News - Brave",
        "url": "https://www.cbc.ca/news/business/data-breach-2026-1.7400000",
        "text": (
            "Major data breach exposes millions of Canadians' records\n"
            "A cyberattack on a large Canadian loyalty-points company has exposed the names, emails and "
            "partial card numbers of about 4.2 million customers, the company confirmed on Tuesday. "
            "The breach was discovered on Nov. 18 after unusual traffic was spotted on a server that stored "
            "old customer backups. The company says passwords were encrypted and that no full credit card "
            "numbers were taken. The Office of the Privacy Commissioner of Canada has opened an investigation. "
            "Security experts say customers should watch for phishing emails that use their real names, "
            "turn on two-factor authentication and change reused passwords. The company is offering two years "
            "of free credit monitoring. A class-action lawsuit was filed in Ontario Superior Court on Wednesday. "
            "Experts say breaches like this are rising because companies keep old data they no longer need."
        ),
    },
}

LAST_DOC = {"kind": "slides", "path": "C:/Users/ziada/Documents/Jarvis Docs/Data Breach.pptx",
            "theme": "modern", "spec": {"title": "Data Breach", "sections": []}}

# What each tool "did". {args} fields are filled in from the call.
RESULTS = {
    "brief_document": "Brief ready on the right of his screen: 5 key points about the data breach article "
                      "(4.2 million customers, names/emails/partial card numbers, privacy commissioner "
                      "investigating, use 2FA, free credit monitoring).",
    "read_screen": "Read \"{title}\" via the browser extension. Text:\n{text}",
    "look_at_screen": "The screen shows a news article with a photo of a laptop showing a padlock.",
    "make_document": "Made the slides and opened them: Documents/Jarvis Docs/{topic}.pptx (7 slides).",
    "write_script": "Wrote the presenter script (7 slides, about 5 min) and opened it: Documents/Jarvis Docs/"
                    "Data Breach - script.docx.",
    "check_email": "2 matching emails; newest first: Prof. Lee - Lab 4 marks posted (Tue 14:02); "
                   "Canvas - Assignment due Friday (Tue 09:15).",
    "restyle_document": "Restyled the deck with the {style} theme and opened it.",
    "make_file": "Wrote {name} and opened it.",
    "split_screen": "Put the two windows side by side.",
    "show_diagram": "Drew the first step on the whiteboard. 4 steps in total. Say 'next' for the next one.",
    "whiteboard_step": "Showing step 2 of 4.",
    "make_3d_model": "Made the model and opened it in the 3D viewer.",
    "open_website": "Opened it in Brave.",
    "play_music": "Playing it now.",
    "media": "Done.",
    "open_app": "Opened {name}.",
    "set_volume": "Volume set.",
    "find_files": "Found 2 files: Documents/School/Thermo/Thermo notes week 3.docx; "
                  "Documents/School/Thermo/Thermo lecture 5.pdf",
    "read_file": "The file is about the first law of thermodynamics and heat engines.",
    "organize_folder": "Sorted 34 files into Images, Documents, Installers and Zips. Say 'undo that' to put them back.",
    "undo_files": "Put 34 files back where they were.",
    "open_folder": "Opened the folder.",
    "open_file": "Opened the file.",
    "canvas_due": "Due this week: Thermo lab report (Thu 11:59 PM), Calculus problem set 8 (Fri 5 PM).",
    "canvas_download": "Downloaded 6 new files to Documents/School.",
    "quiz_me": "Quiz ready. First question: What does the first law of thermodynamics say about energy?",
    "set_reminder": "Reminder set.",
    "set_timer": "Timer set.",
    "set_alarm": "Alarm set for 7:00 AM tomorrow.",
    "get_calendar_events": "Tomorrow: Calculus 10:00 AM, Thermo lab 2:00 PM.",
    "get_weather": "Courtice: -2 C, light snow, high of 1.",
    "remember": "Saved.",
    "test_phone_alerts": "Sent a test message to his phone on Telegram. Ask him if it arrived.",
    "calculate": "36",
    "web_search": "Results: (1) CBC: data breach exposes 4.2M records. (2) Global News: what to do after a breach.",
    "test_pointer": "The pointer is showing in the middle of his screen for 6 seconds. Ask if he can see it.",
    "point_at": "Pointing at \"Design\" (ui automation). Tell him what it is in a few words.",
    "get_news": "Top stories: data breach at a loyalty company; Bank of Canada rate hold.",
}
DEFAULT = "Done."


class Recorder:
    """Takes the place of skills.run: notes each call and answers it."""

    def __init__(self, screen=None):
        self.calls = []
        self.screen = screen or {}

    def __call__(self, name, args):
        args = dict(args or {})
        self.calls.append((name, args))
        fields = {"title": self.screen.get("title", "the window"), "text": self.screen.get("text", "")[:2000],
                  "topic": args.get("topic", "Presentation"), "style": args.get("style", "corporate"),
                  "name": args.get("name") or args.get("app") or args.get("filename") or "it"}
        out = RESULTS.get(name, DEFAULT)
        try:
            out = out.format(**fields)
        except (KeyError, IndexError):
            pass
        if name == "read_screen" and not self.screen:
            out = "Nothing readable on the screen (just the desktop)."
        print(f"    [dry run] {name} {args}")
        return out


def fake_read(screen):
    """sight.read stand-in: the article on his screen, or an empty desktop."""
    def read(want_code=False):
        from skills import sight
        if not screen:
            return {"title": "Desktop", "url": "", "text": "", "selection": "", "html": "", "how": "none"}
        sight.last.update(title=screen["title"], url=screen["url"], text=screen["text"], at=time.time())
        return {"title": screen["title"], "url": screen["url"], "text": screen["text"], "selection": "",
                "html": "", "how": "extension"}
    return read
