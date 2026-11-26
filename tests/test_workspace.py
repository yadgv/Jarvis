"""Doc workspace: brief an article, split screen, edit together."""
import json
import os
import types
import urllib.error
import urllib.request

import pytest

import config
from skills import workspace

ARTICLE = """<html><head><title>Why breadboards still matter | Hackaday</title><script>var x=1</script></head>
<body><nav><a>Home</a><a>Projects</a></nav>
<h1>Why breadboards still matter</h1>
<p>Breadboards let you build a circuit without soldering, which makes trying ideas quick and cheap for students.</p>
<p>Each row of five holes is connected underneath by a metal clip, and the long rails carry power and ground.</p>
<ul><li>Keep wires short and colour coded</li><li>Check the rail split in the middle</li></ul>
<footer>Copyright 2026</footer></body></html>"""

BRIEF = "# Breadboards\n**TL;DR:** quick circuits without solder.\n\n## Key points\n- rows of five are connected\n\n## Tips\n- short wires\n"


def test_reads_the_article_not_the_menus():
    title, blocks = workspace.read_html(ARTICLE)
    assert title.startswith("Why breadboards still matter")
    text = " ".join(t for _, t in blocks)
    assert "metal clip" in text and "Keep wires short" in text
    assert "Home" not in text and "Copyright" not in text and "var x" not in text


@pytest.fixture
def ws(monkeypatch, tmp_path):
    from skills import files
    monkeypatch.setattr(files, "_folder", lambda name: str(tmp_path))
    monkeypatch.setattr(files, "_log", lambda *a, **k: None)
    monkeypatch.setattr(workspace, "_ws", dict(workspace._ws, doc="", doc_version=0, file="", text="", busy=""))
    panes = []
    monkeypatch.setattr(workspace, "open_pane", lambda pane, side: panes.append((pane, side)))
    calls = []

    def complete(system, user, **k):
        calls.append((system, user))
        if system == workspace.EDIT_SYSTEM:
            return "```markdown\n" + BRIEF.replace("## Tips\n- short wires\n", "## Tips\n- short wires\n- add a point about costs\n") + "```"
        return BRIEF
    from brain import llm
    monkeypatch.setattr(llm, "complete", complete)
    return types.SimpleNamespace(panes=panes, calls=calls, folder=tmp_path)


def _page(monkeypatch):
    class R:
        status_code, text, content = 200, ARTICLE, ARTICLE.encode()
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            pass
    monkeypatch.setattr(workspace.requests, "get", lambda url, **k: R())


def test_brief_a_link_splits_reader_and_brief(ws, monkeypatch):
    _page(monkeypatch)
    out = workspace.brief_document({"source": "https://hackaday.com/breadboards"})
    assert ws.panes == [("source", "left"), ("brief", "right")]     # split screen
    assert "right half" in out and "Key points" in out
    assert "metal clip" in ws.calls[0][1]                           # the article went to the model
    saved = os.path.join(ws.folder, "Jarvis Docs", "Why breadboards still matter - brief.md")
    assert open(saved, encoding="utf-8").read().startswith("# Breadboards")
    assert workspace.state()["by"] == "jarvis"


def test_brief_of_what_is_on_screen_snaps_his_window_left(ws, monkeypatch):
    _page(monkeypatch)
    snapped = []
    monkeypatch.setattr(workspace, "on_screen",
                        lambda: (workspace._url_source("https://hackaday.com/x"), 4242))
    monkeypatch.setattr(workspace, "_snap_left", snapped.append)
    out = workspace.brief_document({})
    assert snapped == [4242] and ws.panes == [("brief", "right")]   # his browser left, brief right
    assert "article on the left" in out


def test_his_window_skips_jarvis():
    wins = [(1, "Jarvis brief"), (2, "Servo · Jarvis 3D viewer"), (3, "Why breadboards matter - Google Chrome")]
    assert workspace.his_window(wins) == (3, "Why breadboards matter - Google Chrome")
    assert workspace.BROWSERS.search("Article - Personal - Microsoft Edge")


def test_edit_by_voice_and_by_typing(ws, monkeypatch):
    _page(monkeypatch)
    workspace.brief_document({"source": "https://hackaday.com/b"})
    out = workspace.edit_brief({"change": "add a point about costs"})
    assert "Changed" in out and "add a point about costs" in workspace.state()["doc"]
    assert "```" not in workspace.state()["doc"]
    # He types in the window: the page posts with the version it started from.
    base = workspace.state()["doc_version"]
    link = workspace.url()
    req = urllib.request.Request(link + "doc", data=json.dumps({"text": "# Mine\n", "base": base}).encode(),
                                 method="POST")
    assert json.loads(urllib.request.urlopen(req, timeout=5).read())["ok"]
    assert workspace.state()["doc"] == "# Mine\n" and workspace.state()["by"] == "you"
    assert "Mine" in workspace.read_brief()
    stale = urllib.request.Request(link + "doc", data=json.dumps({"text": "old", "base": base}).encode(), method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:      # Jarvis (or he) changed it since: not overwritten
        urllib.request.urlopen(stale, timeout=5)
    assert e.value.code == 409 and workspace.state()["doc"] == "# Mine\n"


def test_save_as_word(ws, monkeypatch):
    pytest.importorskip("docx")
    _page(monkeypatch)
    workspace.brief_document({"source": "https://hackaday.com/b"})
    out = workspace.save_brief_as_word()
    assert out.startswith("Saved as Word")
    import docx
    path = os.path.join(ws.folder, "Jarvis Docs", "Why breadboards still matter - brief.docx")
    text = [p.text for p in docx.Document(path).paragraphs]
    assert "Breadboards" in text and "Key points" in text and "rows of five are connected" in text


def test_page_and_tools():
    page = open(workspace.PAGE_FILE, encoding="utf-8").read()
    assert "JARVIS // BRIEF" in page and "/doc" in page and "pane" in page
    import skills
    for ask in ("brief this article", "make section 2 shorter", "summarise this pdf"):
        assert "brief_document" in skills.pick_tools(ask) or "edit_brief" in skills.pick_tools(ask), ask
    assert {"edit_brief", "brief_document"} <= skills.pick_tools("make section 2 shorter") | skills.pick_tools("brief this article")


def test_nothing_to_brief(ws, monkeypatch):
    monkeypatch.setattr(workspace, "on_screen", lambda: (_ for _ in ()).throw(ValueError("I can't see a window")))
    assert "Couldn't open it" in workspace.brief_document({})
    assert "no brief open" in workspace.edit_brief({"change": "shorter"})
