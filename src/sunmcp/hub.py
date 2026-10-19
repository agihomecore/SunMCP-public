"""MCPHub: connects to several MCP servers over stdio and exposes their tools as one flat list."""

from __future__ import annotations

from contextlib import AsyncExitStack
from collections.abc import Awaitable, Callable
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import ServerConfig

SEP = "__"


def _pick(obj: Any, *names: str, default: Any = None) -> Any:
    """MCP SDK 2.x uses snake_case fields, 1.x used camelCase. Accept both."""
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v
    return default


class MCPHub:
    def __init__(self, servers: dict[str, ServerConfig]) -> None:
        self._configs = servers
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: list[dict[str, Any]] = []
        self._builtin: dict[str, Callable[[dict[str, Any]], Awaitable[tuple[str, bool]]]] = {}
        self._builtin_specs: list[dict[str, Any]] = []

    def register_builtin(
        self,
        spec: dict[str, Any],
        handler: Callable[[dict[str, Any]], Awaitable[tuple[str, bool]]],
    ) -> None:
        """Add an in-process tool (no MCP server). Name must not contain '__'."""
        self._builtin[spec["name"]] = handler
        self._builtin_specs.append(spec)

    async def __aenter__(self) -> "MCPHub":
        try:
            for name, cfg in self._configs.items():
                try:
                    params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env)
                    read, write = await self._stack.enter_async_context(stdio_client(params))
                    session = await self._stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                except Exception as e:
                    raise RuntimeError(
                        f"MCP server '{name}' failed to start "
                        f"({cfg.command} {' '.join(cfg.args)}): {e}"
                    ) from e
                self._sessions[name] = session
            await self.refresh_tools()
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.aclose()

    async def refresh_tools(self) -> None:
        tools: list[dict[str, Any]] = []
        for server, session in self._sessions.items():
            result = await session.list_tools()
            for t in result.tools:
                tools.append(
                    {
                        "name": f"{server}{SEP}{t.name}",
                        "description": t.description or "",
                        "input_schema": _pick(
                            t, "input_schema", "inputSchema", default={"type": "object", "properties": {}}
                        ),
                    }
                )
        self._tools = tools

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [*self._builtin_specs, *self._tools]

    async def call(self, qualified_name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Returns (text, is_error). Never raises for tool-level problems, so the model can recover."""
        if qualified_name in self._builtin:
            try:
                return await self._builtin[qualified_name](arguments)
            except Exception as e:
                return f"tool call failed: {e}", True
        server, _, tool = qualified_name.partition(SEP)
        session = self._sessions.get(server)
        if session is None or not tool:
            return f"unknown tool: {qualified_name}", True
        try:
            result = await session.call_tool(tool, arguments)
        except Exception as e:  # transport/protocol error
            return f"tool call failed: {e}", True
        parts = [getattr(c, "text", None) or f"[{getattr(c, 'type', 'content')}]" for c in result.content]
        return "\n".join(parts), bool(_pick(result, "is_error", "isError", default=False))
