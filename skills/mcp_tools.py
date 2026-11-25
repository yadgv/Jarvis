"""Use any MCP server's tools (Model Context Protocol, modelcontextprotocol.io).

List servers in mcp_servers.json next to config.py, in the same format as
Claude Desktop's config, so examples can be pasted straight in:

    {"mcpServers": {
        "files": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me/Documents"]},
        "home":  {"url": "http://homeassistant.local:8123/api/mcp", "headers": {"Authorization": "Bearer ..."}}
    }}

Each server's tools become Jarvis tools named <server>__<tool>. Servers start
in the background when Jarvis starts; one that fails is skipped (see the log).
Needs: pip install mcp
"""
import asyncio
import json
import os
import re
import threading
from contextlib import AsyncExitStack

import config

CONFIG_FILE = getattr(config, "MCP_CONFIG", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                         "mcp_servers.json"))
CALL_TIMEOUT = 120
SKILLS = []  # filled in by start(); registered with skills.register()

_loop = None
_sessions = {}  # server name -> ClientSession
_ready = threading.Event()


def load_servers() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"[mcp] couldn't read {CONFIG_FILE}: {e}")
        return {}
    servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
    return {k: v for k, v in servers.items() if isinstance(v, dict) and not v.get("disabled")}


def tool_name(server: str, tool: str) -> str:
    """Claude allows [a-zA-Z0-9_-], up to 64 characters."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server}__{tool}")[:64]


def result_text(result) -> str:
    parts = []
    for c in getattr(result, "content", None) or []:
        if getattr(c, "type", "") == "text":
            parts.append(c.text)
        else:
            parts.append(f"[{getattr(c, 'type', 'content')} not shown]")
    text = "\n".join(parts) or "Done."
    if getattr(result, "is_error", False) or getattr(result, "isError", False):
        text = "Error: " + text
    return text[:6000]


def _make_skill(server, tool):
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {"type": "object"}
    name = tool_name(server, tool.name)

    def run(args):
        session = _sessions.get(server)
        if session is None:
            return f"The {server} tool server isn't connected."
        fut = asyncio.run_coroutine_threadsafe(session.call_tool(tool.name, args), _loop)
        return result_text(fut.result(timeout=CALL_TIMEOUT))

    return {
        "name": name,
        "description": f"[{server}] {(tool.description or tool.name)[:900]}",
        "parameters": schema,
        "run": run,
    }


async def _connect(stack, name, spec):
    from mcp import ClientSession
    if spec.get("url"):
        import httpx
        from mcp.client.streamable_http import streamable_http_client
        client = await stack.enter_async_context(httpx.AsyncClient(headers=spec.get("headers") or {}, timeout=60))
        streams = await stack.enter_async_context(streamable_http_client(spec["url"], http_client=client))
    else:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = {**os.environ, **(spec.get("env") or {})}
        params = StdioServerParameters(command=spec["command"], args=spec.get("args") or [], env=env)
        streams = await stack.enter_async_context(stdio_client(params))
    session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
    await session.initialize()
    tools = (await session.list_tools()).tools
    _sessions[name] = session
    return [_make_skill(name, t) for t in tools]


async def _main(servers, register):
    async with AsyncExitStack() as stack:
        for name, spec in servers.items():
            try:
                found = await asyncio.wait_for(_connect(stack, name, spec), 60)
                SKILLS.extend(found)
                register(found)
                print(f"[mcp] {name}: {len(found)} tools")
            except Exception as e:
                print(f"[mcp] {name} failed to start: {type(e).__name__}: {e}")
        _ready.set()
        await asyncio.Event().wait()  # keep the servers running until Jarvis exits


def start(register=None) -> bool:
    """Start the servers in mcp_servers.json in the background."""
    global _loop
    servers = load_servers()
    if not servers or _loop is not None:
        _ready.set()
        return False
    try:
        import mcp  # noqa: F401
    except ImportError:
        print('[mcp] mcp_servers.json found, but the MCP library is missing: pip install mcp')
        _ready.set()
        return False
    if register is None:
        import skills
        register = skills.register
    _loop = asyncio.new_event_loop()
    threading.Thread(target=_loop.run_forever, daemon=True, name="mcp").start()
    asyncio.run_coroutine_threadsafe(_main(servers, register), _loop)
    return True
