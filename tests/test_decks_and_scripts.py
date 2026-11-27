"""His own decks: restyle the one open in PowerPoint, write a presenter script, routing (Nov 27 log)."""
import json

import pytest

import config
import skills
from skills import documents, files

SPEC = {"title": "KDgate: Montreal mayor's website", "subtitle": "What happened",
        "sections": [{"heading": "The site", "bullets": ["Launched in May", "Cost $2M", "Went down twice"]},
                     {"heading": "The fallout", "bullets": ["Council vote", "Audit ordered"]},
                     {"heading": "What's next", "bullets": ["New contract", "Public report"], "text": "Due in March."},
                     {"heading": "Lessons", "bullets": ["Test early"]}]}


@pytest.fixture
def his_deck(private_files, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(private_files / "mem"))
    monkeypatch.setattr(files, "open_file", lambda a: None)
    path = private_files / "Documents" / "KDgate Montreal Mayor's Website Controversy.pptx"
    documents.build_slides(SPEC, str(path), "modern")    # made by him (not remembered as Jarvis's)
    return path


def test_layouts_vary_and_deck_reads_back(his_deck):
    from pptx import Presentation
    deck = Presentation(str(his_deck))
    assert len(deck.slides) == 6
    spec = documents.import_pptx(str(his_deck))
    assert spec["title"] == SPEC["title"]
    heads = [s["heading"] for s in spec["sections"]]
    assert heads == ["The site", "The fallout", "What's next", "Lessons"]
    assert "Cost $2M" in spec["sections"][0]["bullets"] and "Audit ordered" in spec["sections"][1]["bullets"]
    # not every slide has the same shapes: three layouts in turn
    from pptx.util import Inches
    assert len(deck.slides[2].shapes) > len(deck.slides[1].shapes)              # cards
    assert any(sh.left == 0 and sh.height == Inches(7.5) for sh in deck.slides[3].shapes)   # side panel


def test_open_office_window_titles(monkeypatch):
    from skills import whiteboard, workspace
    monkeypatch.setattr(documents.sys if hasattr(documents, "sys") else __import__("sys"), "platform", "win32")
    monkeypatch.setattr(whiteboard, "_user32", lambda: None)
    monkeypatch.setattr(workspace, "_windows", lambda u: [
        (1, "J.A.R.V.I.S."), (2, "KDgate Montreal Mayor's Website Controversy.pptx - PowerPoint"),
        (3, "Essay - Compatibility Mode - Word"), (4, "News - Brave")])
    assert documents.open_office_files() == [("KDgate Montreal Mayor's Website Controversy.pptx", "slides"),
                                             ("Essay.docx", "word")]


def test_restyle_his_open_deck_makes_a_copy(his_deck, monkeypatch):
    monkeypatch.setattr(documents, "open_office_files", lambda: [(his_deck.name, "slides")])
    out = documents.restyle_document({"style": "make this presentation prettier"})
    copies = [p for p in his_deck.parent.glob("*.pptx") if p != his_deck]
    assert len(copies) == 1 and "original is untouched" in out and his_deck.exists()
    assert documents.import_pptx(str(copies[0]))["sections"][0]["bullets"][1] == "Cost $2M"
    # "make it corporate" next restyles the copy Jarvis made, in place
    monkeypatch.setattr(documents, "open_office_files", lambda: [(copies[0].name, "slides")])
    documents.restyle_document({"style": "corporate"})
    assert len(list(his_deck.parent.glob("*.pptx"))) == 2


def test_restyle_by_name(his_deck, monkeypatch):
    monkeypatch.setattr(documents, "open_office_files", lambda: [])
    out = documents.restyle_document({"style": "corporate", "file": "KDgate Montreal"})
    assert "corporate" in out and len(list(his_deck.parent.glob("*.pptx"))) == 2


def test_nothing_to_restyle(private_files, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", str(private_files / "mem"))
    monkeypatch.setattr(documents, "open_office_files", lambda: [])
    assert "Ask which file" in documents.restyle_document({"style": "prettier"})


def test_presenter_script(his_deck, monkeypatch):
    from brain import llm
    seen = {}

    def complete(system, user, max_tokens=400, small=True, models=None, check=None):
        seen["prompt"] = user
        out = json.dumps({"title": "x", "slides": [{"slide": h, "say": f"Here I talk about {h}."} for h in
                          ["Title", "The site", "The fallout", "What's next", "Lessons", "Thanks"]]})
        check(out)
        return out
    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(documents, "open_office_files", lambda: [(his_deck.name, "slides")])
    out = documents.write_script({"minutes": 5})
    script = his_deck.parent / "KDgate Montreal Mayor's Website Controversy - script.docx"
    assert script.exists() and "presenter script" in out and "5 min" in out
    assert "Cost $2M" in seen["prompt"]
    import docx
    text = "\n".join(p.text for p in docx.Document(str(script)).paragraphs)
    assert "2. The site" in text and "Here I talk about The fallout." in text


def test_script_goes_in_speaker_notes_of_jarvis_decks(private_files, monkeypatch):
    from brain import llm
    from pptx import Presentation
    monkeypatch.setattr(config, "MEMORY_DIR", str(private_files / "mem"))
    monkeypatch.setattr(files, "open_file", lambda a: None)
    path = documents.make("slides", SPEC, str(private_files / "Documents"), "Mine")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: json.dumps(
        {"slides": [{"slide": "t", "say": "Good morning everyone."}, {"slide": "s", "say": "First, the site."}]}))
    out = documents.write_script({})
    assert "speaker notes" in out
    deck = Presentation(path)
    assert deck.slides[1].notes_slide.notes_text_frame.text == "First, the site."


def test_routing(monkeypatch):
    monkeypatch.setattr(documents, "open_office_files", lambda: [("Deck.pptx", "slides")])
    plan = skills.route("Can you make this presentation prettier?")
    assert plan["direct"][0][0] == "restyle_document" and "make_document" in plan["exclude"]
    assert skills.route("I don't like how repetitive it is")["direct"][0][0] == "restyle_document"
    plan = skills.route("make me a script for the slideshow")
    assert plan["direct"][0][0] == "write_script"
    assert skills.route("write speaker notes for this presentation")["direct"][0][0] == "write_script"
    assert not skills.route("write a python script to rename files")["direct"]
    assert skills.route("Can you tell me any unread emails?")["direct"] == [("check_email", {})]
    assert skills.route("check my inbox")["direct"] == [("check_email", {})]
    assert not skills.route("write an email to my professor")["direct"]


def test_tool_instructions_never_spoken():
    from brain import llm
    for line in ("Tell him in one short sentence; other looks: modern.", "Say so in one short sentence.",
                 "Ask him if it arrived.", "Offer him the corporate look."):
        assert not llm._speakable(line), line
    assert llm._speakable("Done, sir. The deck has a fresh look.")
