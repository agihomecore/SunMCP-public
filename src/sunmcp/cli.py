"""sunmcp CLI: init | tools | run | chat"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import __version__
from .agent import run_turn
from .config import SAMPLE_CONFIG, load_config
from .hub import MCPHub
from .llm import make_backend


def _print_tool(name: str, args: dict, text: str, is_error: bool) -> None:
    flag = "ERR" if is_error else "ok"
    short = text if len(text) < 200 else text[:200] + "..."
    print(f"  [{flag}] {name}({json.dumps(args, ensure_ascii=False)}) -> {short}", file=sys.stderr)


async def _tools(config_path: str) -> int:
    cfg = load_config(config_path)
    async with MCPHub(cfg.servers) as hub:
        if not hub.tools:
            print("no tools found")
        for t in hub.tools:
            print(f"{t['name']}: {t['description']}")
    return 0


async def _run(config_path: str, prompt: str) -> int:
    cfg = load_config(config_path)
    backend = make_backend(cfg.backend)
    async with MCPHub(cfg.servers) as hub:
        print(await run_turn(backend, hub, [], prompt, cfg.system, on_tool=_print_tool))
    return 0


async def _chat(config_path: str) -> int:
    cfg = load_config(config_path)
    backend = make_backend(cfg.backend)
    history: list = []
    async with MCPHub(cfg.servers) as hub:
        print(f"sunmcp {__version__}: {len(hub.tools)} tools. Ctrl-D or /exit to quit.")
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, lambda: input("you> "))
            except EOFError:
                break
            if line.strip() in ("/exit", "/quit"):
                break
            if not line.strip():
                continue
            if line.strip() == "/reset":
                history.clear()
                continue
            answer = await run_turn(backend, hub, history, line, cfg.system, on_tool=_print_tool)
            print(f"ai> {answer}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sunmcp", description="Model-agnostic MCP client")
    p.add_argument("--version", action="version", version=f"sunmcp {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("tools", "chat"):
        s = sub.add_parser(name)
        s.add_argument("-c", "--config", default="sunmcp.json")
    s = sub.add_parser("run", help="one-shot prompt")
    s.add_argument("prompt")
    s.add_argument("-c", "--config", default="sunmcp.json")
    s = sub.add_parser("init", help="write a sample sunmcp.json")
    s.add_argument("-c", "--config", default="sunmcp.json")
    args = p.parse_args(argv)

    if args.cmd == "init":
        path = Path(args.config)
        if path.exists():
            print(f"{path} already exists", file=sys.stderr)
            return 1
        path.write_text(json.dumps(SAMPLE_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path}")
        return 0
    try:
        if args.cmd == "tools":
            return asyncio.run(_tools(args.config))
        if args.cmd == "run":
            return asyncio.run(_run(args.config, args.prompt))
        return asyncio.run(_chat(args.config))
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
