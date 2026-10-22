"""SunMCP: model-agnostic MCP client."""

from .agent import run_turn
from .config import BackendConfig, Config, ServerConfig, VisionConfig, load_config
from .hub import MCPHub
from .thread import GuardedHub, Thread, run_loop, run_step
from .vision import Vision, attach_vision
from .llm import AnthropicBackend, Backend, OpenAICompatBackend, ToolCall, Turn, make_backend

__version__ = "0.3.0"

__all__ = [
    "AnthropicBackend",
    "Backend",
    "BackendConfig",
    "Config",
    "MCPHub",
    "OpenAICompatBackend",
    "ServerConfig",
    "Thread",
    "GuardedHub",
    "run_loop",
    "run_step",
    "ToolCall",
    "Vision",
    "VisionConfig",
    "Turn",
    "attach_vision",
    "load_config",
    "make_backend",
    "run_turn",
]
