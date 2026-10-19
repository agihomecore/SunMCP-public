"""The agent loop: model -> tool calls -> MCP -> model, until the model answers in plain text."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .hub import MCPHub
from .llm import Backend

ToolHook = Callable[[str, dict[str, Any], str, bool], None]


async def run_turn(
    backend: Backend,
    hub: MCPHub,
    history: list[dict[str, Any]],
    user_text: str,
    system: str | None = None,
    max_steps: int = 8,
    on_tool: ToolHook | None = None,
) -> str:
    """Appends to `history` in place and returns the final assistant text."""
    history.append({"role": "user", "content": user_text})
    for _ in range(max_steps):
        turn = await backend.complete(history, hub.tools, system)
        history.append(
            {
                "role": "assistant",
                "content": turn.content,
                "tool_calls": [
                    {"id": c.id, "name": c.name, "arguments": c.arguments} for c in turn.tool_calls
                ],
            }
        )
        if not turn.tool_calls:
            return turn.content
        for call in turn.tool_calls:
            text, is_error = await hub.call(call.name, call.arguments)
            if on_tool:
                on_tool(call.name, call.arguments, text, is_error)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": f"ERROR: {text}" if is_error else text,
                }
            )
    return "(stopped: too many tool steps)"
