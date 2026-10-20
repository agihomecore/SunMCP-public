# Changelog

Format: [Keep a Changelog](https://keepachangelog.com). Versioning: [SemVer](https://semver.org).

## 0.2.8
- `sunmcp box --write --install`: also downloads and sets up the models (runs the `ollama pull` / `ollama create` commands itself). If Ollama is missing it says where to get it. A buyer now needs one command after installing the wheels.

## 0.2.7
- New `sunmcp thread`: the "thread" loop (docs/THREAD.md). Works from plain files (GOAL.md, LOG.md, OUTBOX.jsonl, ANSWERS.jsonl), takes one step per interval, never blocks on a question.
  - Built-in non-blocking `ask` tool (returns at once with the model's assumption) and `thread_log`.
  - Irreversible-looking tools (delete, send, publish, push, pay ...) are blocked and become approval questions; `--allow` / `--deny` tune it.
  - Kill switch: a `STOP` file (`sunmcp thread stop` / `resume`); daily step cap; failed steps are logged and retried with backoff.
  - `--notify "<command>"` receives each new question as JSON on stdin.

## 0.2.6
- `sunmcp box` now writes CPU-only Ollama Modelfiles (`sunbox-chat`, `sunbox-vision`: `num_gpu 0`, `num_ctx 4096`) and uses them. Measured on a 4C/8T laptop: Ollama's default (24% of layers on a weak iGPU, 8192 context) gave 3 tok/s on qwen2.5:3b; CPU-only gave 10.5 tok/s. `--gpu` keeps the stock models.

## 0.2.5
- New `sunmcp box`: detects cores/RAM, picks a tier and models (see docs/HARDWARE.md), prints install commands, `--write` creates sunmcp.json.
- Tiers use physical cores, not threads (found by running on a 4C/8T laptop).
- Default vision model is now `qwen2.5vl:3b` (7B did not answer on CPU-only hardware).

## 0.2.4
- `.env` support: `sunmcp.json`'s sibling `.env` is loaded (never overrides real environment variables). `.env.example` added.

## 0.2.3
- Fix: config files saved with a UTF-8 BOM (Windows PowerShell, Notepad) now load.

## [0.2.2] - 2026-10-20
### Fixed
- First real run of `screen` on a CPU-only PC: qwen2.5vl:7b on a 1568 px screenshot did not answer in 5 min and the error was misleading. Screenshots are now downscaled to `vision.max_side` (default 1024), `vision.timeout` is configurable (default 600 s), and a timeout says so instead of suggesting `ollama pull`.

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
