"""MCP servers' tools become Jarvis tools."""
import json
import os
import sys

import pytest

import skills
from skills import mcp_tools


def test_tool_names_are_safe():
    assert mcp_tools.tool_name("home assistant", "turn.on") == "home_assistant__turn_on"
    assert len(mcp_tools.tool_name("x" * 50, "y" * 50)) == 64


def test_no_config_means_nothing_starts(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_tools, "CONFIG_FILE", str(tmp_path / "missing.json"))
    assert mcp_tools.start(register=lambda s: None) is False


def test_reads_claude_desktop_format(monkeypatch, tmp_path):
    f = tmp_path / "mcp.json"
    f.write_text(json.dumps({"mcpServers": {"a": {"command": "x"}, "b": {"command": "y", "disabled": True}}}))
    monkeypatch.setattr(mcp_tools, "CONFIG_FILE", str(f))
    assert list(mcp_tools.load_servers()) == ["a"]


def test_register_skips_duplicates():
    before = len(skills.SKILLS)
    skills.register([{"name": "web_search", "description": "", "parameters": {}, "run": None}])
    assert len(skills.SKILLS) == before


def test_real_stdio_server(monkeypatch, tmp_path):
    pytest.importorskip("mcp.server.mcpserver")
    import threading
    server = os.path.join(os.path.dirname(__file__), "fixtures", "echo_mcp_server.py")
    found = []
    monkeypatch.setattr(mcp_tools, "_loop", None)
    monkeypatch.setattr(mcp_tools, "_ready", threading.Event())
    f = tmp_path / "mcp.json"
    f.write_text(json.dumps({"mcpServers": {"echo": {"command": sys.executable, "args": [server]}}}))
    monkeypatch.setattr(mcp_tools, "CONFIG_FILE", str(f))
    assert mcp_tools.start(register=found.extend)
    assert mcp_tools._ready.wait(60)
    tool = next(s for s in found if s["name"] == "echo__shout")
    assert tool["run"]({"text": "hello"}) == "HELLO"
    mcp_tools._loop.call_soon_threadsafe(mcp_tools._loop.stop)
