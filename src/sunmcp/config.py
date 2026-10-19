"""Config loading. JSON file, no magic."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SAMPLE_CONFIG: dict[str, Any] = {
    "backend": {
        "type": "ollama",
        "model": "qwen2.5:7b",
        "base_url": "http://localhost:11434/v1",
    },
    "vision": {
        "enabled": True,
        "model": "qwen2.5vl:7b",
        "base_url": "http://localhost:11434/v1",
        "tool": True,
    },
    "system": "You are a helpful assistant. Use the available tools when they help.",
    "servers": {
        "demo": {"command": "python", "args": ["examples/demo_server.py"]},
    },
}


@dataclass
class ServerConfig:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


@dataclass
class BackendConfig:
    type: str = "ollama"  # ollama | lmstudio | openai | anthropic
    model: str = "qwen2.5:7b"
    base_url: str | None = None
    api_key_env: str | None = None
    max_tokens: int = 2048


@dataclass
class VisionConfig:
    """Screenshot + vision model (default: Qwen2.5-VL on Ollama). Local only unless you change base_url."""

    enabled: bool = True
    model: str = "qwen2.5vl:7b"
    base_url: str = "http://localhost:11434/v1"
    api_key_env: str | None = None
    tool: bool = True  # expose `screenshot` to the chat model so it can look when it needs to
    max_tokens: int = 1024
    max_side: int = 1024  # screenshots are downscaled to this many px on the long side (speed on CPU)
    timeout: float = 600.0  # seconds to wait for the vision model


@dataclass
class Config:
    backend: BackendConfig = field(default_factory=BackendConfig)
    servers: dict[str, ServerConfig] = field(default_factory=dict)
    system: str | None = None
    vision: VisionConfig = field(default_factory=VisionConfig)


def parse_config(data: dict[str, Any]) -> Config:
    b = data.get("backend", {})
    backend = BackendConfig(
        type=b.get("type", "ollama"),
        model=b.get("model", "qwen2.5:7b"),
        base_url=b.get("base_url"),
        api_key_env=b.get("api_key_env"),
        max_tokens=int(b.get("max_tokens", 2048)),
    )
    servers: dict[str, ServerConfig] = {}
    for name, s in (data.get("servers") or {}).items():
        if "__" in name:
            raise ValueError(f"server name {name!r} must not contain '__'")
        if "command" not in s:
            raise ValueError(f"server {name!r} needs a 'command'")
        servers[name] = ServerConfig(
            command=s["command"], args=list(s.get("args", [])), env=s.get("env")
        )
    v = data.get("vision", {})
    vision = VisionConfig(
        enabled=bool(v.get("enabled", True)),
        model=v.get("model", "qwen2.5vl:7b"),
        base_url=v.get("base_url", "http://localhost:11434/v1"),
        api_key_env=v.get("api_key_env"),
        tool=bool(v.get("tool", True)),
        max_tokens=int(v.get("max_tokens", 1024)),
        max_side=int(v.get("max_side", 1024)),
        timeout=float(v.get("timeout", 600)),
    )
    return Config(backend=backend, servers=servers, system=data.get("system"), vision=vision)


def load_config(path: str | Path) -> Config:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p} (run `sunmcp init` to create one)")
    return parse_config(json.loads(p.read_text(encoding="utf-8")))
