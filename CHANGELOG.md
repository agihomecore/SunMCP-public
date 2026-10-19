# Changelog

Format: [Keep a Changelog](https://keepachangelog.com). Versioning: [SemVer](https://semver.org).

## [0.2.1] - 2026-10-20
### Fixed
- Model server HTTP errors (e.g. Ollama 400 "does not support tools") now show the server's message and a hint, not a raw traceback. Found on first real run on Windows (Python 3.14, mcp 2.3.0).
- Unreachable model server prints a clear error.

## [0.2.0] - 2026-10-20
### Added
- Vision on by default: Qwen2.5-VL (`qwen2.5vl:7b`, local Ollama). `sunmcp screen "question"`, `/screen` in chat,
  and a `screenshot` tool the model can call when it needs to look. Needs `pip install "sunmcp[screen]"`.
- Built-in in-process tools via `MCPHub.register_builtin`.

## [0.1.0] - 2026-10-19
### Added
- MCP hub for multiple stdio servers with namespaced tools.
- Backends: Ollama, LM Studio, OpenAI-compatible, Anthropic (bring your own key).
- Agent loop, CLI (`init`, `tools`, `run`, `chat`), library API.
