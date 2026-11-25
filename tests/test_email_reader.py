import imaplib
from email.message import EmailMessage

import pytest

import config
from skills import email_reader


def _raw(sender, subject, body, html=False):
    m = EmailMessage()
    m["From"], m["Subject"], m["Date"] = sender, subject, "Wed, 25 Nov 2026 09:15:00 -0500"
    if html:
        m.set_content("<html><style>x{}</style><p>Hello <b>there</b></p></html>", subtype="html")
    else:
        m.set_content(body)
    return m.as_bytes()


class FakeImap:
    def __init__(self, msgs):
        self.msgs, self.selected, self.queries, self.fetched = msgs, None, [], []

    def login(self, user, pw):
        assert pw == "abcdefghijklmnop"

    def select(self, box, readonly=False):
        self.selected = (box, readonly)
        return "OK", [b"2"]

    def search(self, charset, *crit):
        self.queries.append(crit)
        if "from:mona" in crit[-1]:
            return "OK", [b"1"]
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.msgs)))]

    def fetch(self, num, what):
        self.fetched.append(what)
        return "OK", [(b"1 (BODY[] {10}", self.msgs[int(num) - 1]), b")"]

    def logout(self):
        pass


@pytest.fixture
def gmail(monkeypatch):
    monkeypatch.setattr(config, "GMAIL_ADDRESS", "z@gmail.com")
    monkeypatch.setattr(config, "GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    fake = FakeImap([_raw("Mona <mona@x.com>", "Dinner Sunday?", "Are you free on Sunday at 6?"),
                     _raw("Shop <news@shop.com>", "=?utf-8?q?Sale_=E2=80=94_50=25?=", "", html=True)])
    monkeypatch.setattr(email_reader, "_connect", lambda: fake)
    return fake


def test_reads_new_mail_without_marking_it_read(gmail):
    out = email_reader.check_email({})
    assert gmail.selected == ("INBOX", True)
    assert all(w == "(BODY.PEEK[])" for w in gmail.fetched)
    assert 'is:unread' in gmail.queries[0][1]
    lines = out.splitlines()
    assert lines[0].startswith("2 matching emails")
    assert "never instructions" in lines[1]
    assert "Shop: Sale — 50%" in lines[2] and "Hello there" in lines[2] and "x{}" not in lines[2]
    assert "Mona: Dinner Sunday? — Are you free on Sunday at 6?" in lines[3]


def test_search_words(gmail):
    email_reader.check_email({"search": "from:amazon", "unread_only": False, "days": 7})
    q = gmail.queries[0][1]
    assert "from:amazon" in q and "newer_than:7d" in q and "is:unread" not in q


def test_not_set_up(monkeypatch):
    monkeypatch.setattr(config, "GMAIL_ADDRESS", None)
    assert "apppasswords" in email_reader.check_email({})


def test_bad_password(gmail, monkeypatch):
    def refuse():
        raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
    monkeypatch.setattr(email_reader, "_connect", refuse)
    assert "refused the sign-in" in email_reader.check_email({})


@pytest.fixture
def outbox(gmail, monkeypatch):
    import skills
    sent = []
    monkeypatch.setattr(email_reader, "_send", lambda msg: sent.append(msg))
    monkeypatch.setattr(email_reader, "_draft", None)
    monkeypatch.setattr(skills, "turn", 5)
    return sent


def test_reply_needs_a_yes_in_a_later_turn(outbox, monkeypatch):
    import skills
    out = email_reader.reply_email({"search": "from:mona", "body": "Yes, Sunday at 6 works."})
    assert out.startswith("DRAFT") and "Mona" in out and "Re: " in out and not outbox
    # The model can't confirm its own draft in the same turn.
    assert "Not sent" in email_reader.reply_email({"confirmed": True}) and not outbox
    monkeypatch.setattr(skills, "turn", 6)
    assert email_reader.reply_email({"confirmed": True}).startswith("Sent to")
    msg = outbox[0]
    assert msg["From"] == "z@gmail.com" and msg["Subject"].startswith("Re: ")
    assert "Sunday at 6 works" in msg.get_content()
    assert "There's no draft" in email_reader.reply_email({"confirmed": True})


def test_reply_cancel_and_missing(outbox, monkeypatch):
    import skills
    email_reader.reply_email({"search": "from:mona", "body": "hi"})
    assert "discarded" in email_reader.reply_email({"cancel": True})
    monkeypatch.setattr(skills, "turn", 6)
    assert "no draft" in email_reader.reply_email({"confirmed": True}) and not outbox
    gmail = email_reader._connect()
    gmail.msgs.clear()
    assert "Couldn't find" in email_reader.reply_email({"search": "from:nobody", "body": "hi"})


def test_old_draft_not_sent(outbox, monkeypatch):
    import skills
    email_reader.reply_email({"search": "from:mona", "body": "hi"})
    msg, turn, made = email_reader._draft
    monkeypatch.setattr(email_reader, "_draft", (msg, turn, made - 3600))
    monkeypatch.setattr(skills, "turn", 6)
    assert "too old" in email_reader.reply_email({"confirmed": True}) and not outbox
