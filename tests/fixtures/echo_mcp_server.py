"""A tiny MCP server for tests: one 'shout' tool."""
from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def shout(text: str) -> str:
    """Repeat the text in capitals."""
    return text.upper()


if __name__ == "__main__":
    server.run()
