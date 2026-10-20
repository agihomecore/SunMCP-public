# SunMCP

Model-agnostic **MCP client**. Connect any [MCP](https://modelcontextprotocol.io) server to a **local model (Ollama / Qwen / LM Studio)**, OpenAI, or Anthropic, from one small CLI. Your data stays on your machine when you use a local model.

- Several MCP servers at once (stdio), tools are namespaced as `server__tool`
- Backends: `ollama`, `lmstudio`, `openai`, `anthropic` (bring your own key)
- Agent loop with tool-call error recovery and a step limit
- ~500 lines, no framework, MIT

## Vision (screenshots)

On by default, local, no cloud: Qwen2.5-VL through Ollama.

```bash
ollama pull qwen2.5vl:3b
pip install "sunmcp[screen]"
sunmcp screen "what error is on my screen?"   # by command
```

In `sunmcp chat` use `/screen <question>`. The chat model also gets a `screenshot` tool and calls it when it needs to look.
Nothing is captured unless you ask or the model calls the tool. Turn it off with `"vision": {"enabled": false}`, or only the tool with `"tool": false`.

## Install

```bash
pip install sunmcp          # after first PyPI release
# or from source
git clone <this repo> && cd sunmcp && pip install -e .
```

## 60 seconds

```bash
sunmcp init                 # writes sunmcp.json (Ollama + demo server)
sunmcp tools                # list tools from all configured servers
sunmcp run "what is 2+3? use the tool"
sunmcp chat                 # interactive; /reset clears history, /exit quits
```

`sunmcp.json`:

```json
{
  "backend": {"type": "ollama", "model": "qwen2.5:7b"},
  "system": "Use tools when they help.",
  "servers": {
    "demo": {"command": "python", "args": ["examples/demo_server.py"]},
    "files": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}
  }
}
```

Cloud backends read the key from an environment variable you name:

```json
{"backend": {"type": "anthropic", "model": "claude-sonnet-5-5", "api_key_env": "ANTHROPIC_API_KEY"}}
```

## Use as a library

```python
from sunmcp import MCPHub, load_config, make_backend, run_turn

cfg = load_config("sunmcp.json")
backend = make_backend(cfg.backend)
async with MCPHub(cfg.servers) as hub:
    print(await run_turn(backend, hub, [], "hello", cfg.system))
```

## SunMCP Pro

The core is free. **Pro** adds a Telegram bridge, persistent sessions (SQLite) and priority support with versioned releases. See the project page for details.

## The thread (work without commands)

```
sunmcp thread init              # creates thread/GOAL.md and LOG.md
# edit thread/GOAL.md, then:
sunmcp thread run --interval 900 --notify "python tell_me.py"
sunmcp thread status            # open questions
sunmcp thread answer q1 "yes, the 12 TB"
sunmcp thread stop              # kill switch (resume to continue)
```

Each step starts from the files, does one useful thing with your tools, appends to `LOG.md`. A question never blocks the work: the model states its assumption and goes on; your answer corrects course at the next step. Tools that look irreversible are blocked and turned into approval questions. Details: docs/THREAD.md.

## Compatibility

Tested with `mcp` SDK 2.2. Not affiliated with Anthropic; "MCP" refers to the open Model Context Protocol.

## License

MIT, see [LICENSE](LICENSE).

## Hardware
See [docs/HARDWARE.md](docs/HARDWARE.md) for support tiers and measured numbers.

## Secrets
Put API keys in a `.env` next to `sunmcp.json` (see `.env.example`); reference them by name with `api_key_env`. `.env` is git-ignored.

## Box mode
`sunmcp box` detects your machine and picks models for it; `sunmcp box --write` creates `sunmcp.json`. No model names to type.
