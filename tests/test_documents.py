"""Word, slides, Excel, PDF and charts from a sentence (skills/documents.py)."""
import json
import zipfile

import pytest

from skills import documents, files

SPEC = {"title": "Thermodynamics: the first law", "subtitle": "Study notes",
        "sections": [{"heading": "Energy is conserved", "bullets": ["dU = Q - W", "Closed systems"],
                      "text": "The first law says energy can’t be made or destroyed."},
                     {"heading": "Units", "bullets": ["Joules", "kJ/kg for specific energy, 25°C"]}],
        "table": {"headers": ["Course", "Mark"], "rows": [["Thermo", "88"], ["Digital Systems", "92"],
                                                          ["EE Math", "79"]]},
        "chart": {"type": "bar", "title": "Marks", "labels": ["Thermo", "Digital", "Math"],
                  "series": [{"name": "Mark", "values": [88, 92, 79]}]}}


@pytest.fixture
def model(monkeypatch):
    asked = []

    def complete(system, user, max_tokens=400, small=True, models=None, check=None):
        asked.append(user)
        return "Here:\n```json\n" + json.dumps(SPEC) + "\n```"
    from brain import llm
    monkeypatch.setattr(llm, "complete", complete)
    opened = []
    monkeypatch.setattr(files, "open_file", lambda a: opened.append(a["path"]) or "Opened.")
    return asked, opened


@pytest.mark.parametrize("kind,ext", [("word", ".docx"), ("slides", ".pptx"), ("excel", ".xlsx"), ("pdf", ".pdf")])
def test_each_kind(model, private_files, kind, ext):
    asked, opened = model
    out = documents.make_document({"kind": kind, "topic": "the first law of thermo"})
    path = private_files / "Documents" / ("Thermodynamics the first law" + ext)
    assert path.exists(), out
    assert "Saved Documents/" in out and opened == [str(path)]
    if kind == "word":
        import docx
        text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
        assert "Energy is conserved" in text and "can't be made" in text  # curly quote made plain
    if kind == "slides":
        import pptx
        deck = pptx.Presentation(str(path))
        assert len(deck.slides) == 4  # title, 2 sections, chart
        assert any(sh.has_chart for sh in deck.slides[3].shapes)
    if kind == "excel":
        import openpyxl
        ws = openpyxl.load_workbook(str(path)).active
        assert ws["B2"].value == 88 and len(ws._charts) == 1
    if kind == "pdf":
        assert path.read_bytes().startswith(b"%PDF")


def test_slides_from_his_notes(model, private_files):
    asked, _ = model
    (private_files / "Documents" / "thermo notes.txt").write_text("Entropy of an isolated system never decreases.")
    out = documents.make_document({"kind": "powerpoint", "source": "thermo notes.txt"})
    assert "slides" in out
    assert "Entropy of an isolated system" in asked[0] and "data only" in asked[0]


def test_bad_model_answer(monkeypatch, private_files):
    from brain import llm
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "Sorry, I can't.")
    assert "Couldn't make it" in documents.make_document({"kind": "word", "topic": "x"})


def test_chart_pops_up_and_saves(private_files):
    from skills import whiteboard as wb
    out = documents.show_chart({"title": "My marks", "labels": ["Thermo", "Digital", "Math"],
                                "values": [88, 92, 79], "save": True})
    assert "whiteboard" in out and "My marks.xlsx" in out
    assert wb._board["title"] == "My marks" and "<rect" in wb._board["svg"] and "92" in wb._board["svg"]
    out = documents.show_chart({"title": "Grades", "type": "line", "labels": ["W1", "W2"],
                                "series": [{"name": "Me", "values": [70, 80]}, {"name": "Avg", "values": [65, 72]}]})
    assert wb._board["steps"] == ["Me", "Avg"] and 'class="wire"' in wb._board["svg"]
    documents.show_chart({"title": "Time", "type": "pie", "labels": ["Study", "Sleep"], "values": [6, 8]})
    assert "Sleep: 8 (57%)" in wb._board["svg"]
    assert "no numbers" in documents.show_chart({"title": "x"})


def test_chart_from_a_csv(private_files):
    from skills import whiteboard as wb
    files.make_file({"name": "marks.csv", "rows": [["Course", "Mark"], ["Thermo", "88"], ["Math", "79"]]})
    documents.show_chart({"title": "Marks", "source": "marks.csv"})
    assert "Thermo" in wb._board["svg"] and "88" in wb._board["svg"]


def test_routing():
    import skills
    for text in ("make slides on my thermo notes", "graph my marks", "write me a cover letter as a word doc",
                 "make a pdf study sheet for digital systems", "put my marks in an excel spreadsheet"):
        picked = skills.pick_tools(text)
        assert {"make_document", "show_chart"} <= picked, text
