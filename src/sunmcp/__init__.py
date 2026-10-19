"""SunMCP: model-agnostic MCP client."""

from .agent import run_turn
from .config import BackendConfig, Config, ServerConfig, load_config
from .hub import MCPHub
from .llm import AnthropicBackend, Backend, OpenAICompatBackend, ToolCall, Turn, make_backend

__version__ = "0.1.0"

__all__ = [
    "AnthropicBackend",
    "Backend",
    "BackendConfig",
    "Config",
    "MCPHub",
    "OpenAICompatBackend",
    "ServerConfig",
    "ToolCall",
    "Turn",
    "load_config",
    "make_backend",
    "run_turn",
]
