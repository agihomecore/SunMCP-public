"""LLM backends behind one tiny interface.

Neutral message format used everywhere in SunMCP:
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{"id","name","arguments"}]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}

Neutral tool spec: {"name", "description", "input_schema"}.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .config import BackendConfig


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Turn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class Backend(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str | None = None,
    ) -> Turn: ...


def _check(r: httpx.Response, who: str) -> None:
    """Turn an HTTP error into a readable RuntimeError that includes what the server said."""
    if r.status_code < 400:
        return
    try:
        body = r.json()
        detail = (body.get("error") or body) if isinstance(body, dict) else body
        if isinstance(detail, dict):
            detail = detail.get("message") or detail
    except ValueError:
        detail = r.text
    detail = str(detail)[:400]
    hint = ""
    if "does not support tools" in detail:
        hint = (
            " Hint: pick a tool-capable chat model in `backend.model` (for example qwen2.5:7b); "
            "keep the vision model only in `vision.model`."
        )
    raise RuntimeError(f"{who} returned HTTP {r.status_code}: {detail}.{hint}")


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except json.JSONDecodeError:
        return {}


class OpenAICompatBackend:
    """Works with Ollama (/v1), LM Studio, OpenAI and any OpenAI-compatible server."""

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        timeout: float = 180.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def convert_messages(messages: list[dict[str, Any]], system: str | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                out.append(
                    {
                        "role": "assistant",
                        "content": m.get("content") or None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["arguments"]),
                                },
                            }
                            for tc in m["tool_calls"]
                        ],
                    }
                )
            elif m["role"] == "tool":
                out.append(
                    {"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]}
                )
            else:
                out.append({"role": m["role"], "content": m.get("content", "")})
        return out

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str | None = None,
    ) -> Turn:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self.convert_messages(messages, system),
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = await self._client.post(
            f"{self.base_url}/chat/completions", json=payload, headers=headers
        )
        _check(r, f"model '{self.model}' at {self.base_url}")
        msg = r.json()["choices"][0]["message"]
        calls = [
            ToolCall(
                id=tc.get("id") or f"call_{i}",
                name=tc["function"]["name"],
                arguments=_parse_args(tc["function"].get("arguments")),
            )
            for i, tc in enumerate(msg.get("tool_calls") or [])
        ]
        return Turn(content=msg.get("content") or "", tool_calls=calls)


class AnthropicBackend:
    """Claude via the public Messages API. Only used if the customer brings their own key."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 2048,
        timeout: float = 180.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m["role"] == "assistant":
                blocks: list[dict[str, Any]] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["arguments"],
                        }
                    )
                out.append({"role": "assistant", "content": blocks})
            elif m["role"] == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": m["tool_call_id"],
                    "content": m["content"],
                }
                # consecutive tool results must live in ONE user message
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
            else:
                out.append({"role": "user", "content": m.get("content", "")})
        return out

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str | None = None,
    ) -> Turn:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": self.convert_messages(messages),
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t["input_schema"],
                }
                for t in tools
            ]
        r = await self._client.post(
            f"{self.base_url}/v1/messages",
            json=payload,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        _check(r, f"Anthropic API (model '{self.model}')")
        text, calls = [], []
        for block in r.json().get("content", []):
            if block["type"] == "text":
                text.append(block["text"])
            elif block["type"] == "tool_use":
                calls.append(ToolCall(block["id"], block["name"], block.get("input") or {}))
        return Turn(content="".join(text), tool_calls=calls)


def make_backend(cfg: BackendConfig) -> Backend:
    key = os.environ.get(cfg.api_key_env) if cfg.api_key_env else None
    if cfg.type in ("ollama", "lmstudio", "openai"):
        defaults = {
            "ollama": "http://localhost:11434/v1",
            "lmstudio": "http://localhost:1234/v1",
            "openai": "https://api.openai.com/v1",
        }
        if cfg.type == "openai" and not key:
            raise ValueError("openai backend needs api_key_env pointing at an env var with the key")
        return OpenAICompatBackend(cfg.model, cfg.base_url or defaults[cfg.type], key)
    if cfg.type == "anthropic":
        if not key:
            raise ValueError("anthropic backend needs api_key_env pointing at an env var with the key")
        return AnthropicBackend(
            cfg.model, key, cfg.base_url or "https://api.anthropic.com", cfg.max_tokens
        )
    raise ValueError(f"unknown backend type: {cfg.type!r}")
