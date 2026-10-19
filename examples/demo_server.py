"""Tiny MCP server used for the demo and the tests (MCP SDK 2.x)."""

from mcp.server.mcpserver import MCPServer

server = MCPServer("demo")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@server.tool()
def shout(text: str) -> str:
    """Return the text in upper case."""
    return text.upper()


if __name__ == "__main__":
    server.run("stdio")
