"""sunmcp CLI: init | box | tools | run | chat | screen | thread"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

from . import __version__
from .agent import run_turn
from .box import box_config, choose_tier, detect_hardware, install_models, modelfiles, report
from .config import SAMPLE_CONFIG, load_config
from .hub import MCPHub
from .llm import make_backend
from .thread import DEFAULT_DENY, Thread, run_loop, shell_notifier
from .vision import Vision, attach_vision


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


async def _screen(config_path: str, question: str | None, monitor: int) -> int:
    cfg = load_config(config_path)
    if not cfg.vision.enabled:
        print("error: vision is disabled in config", file=sys.stderr)
        return 2
    print(await Vision(cfg.vision).look(question, monitor))
    return 0


async def _thread_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    thread = Thread(args.dir)
    thread.goal()  # fail early and readably if there is no GOAL.md
    backend = make_backend(cfg.backend)
    deny = (*DEFAULT_DENY, *args.deny)
    notify = shell_notifier(args.notify) if args.notify else None
    async with MCPHub(cfg.servers) as hub:
        attach_vision(hub, Vision(cfg.vision))
        steps = await run_loop(
            backend, hub, thread, cfg.system, interval=args.interval, once=args.once,
            max_per_day=args.max_per_day, deny=deny, allow=tuple(args.allow), notify=notify,
            on_tool=_print_tool,
        )
    print(f"thread: {steps} step(s) done" + (" (stopped)" if thread.stopped() else ""))
    return 0


def _thread_control(args: argparse.Namespace) -> int:
    thread = Thread(args.dir)
    if args.action == "init":
        made = thread.init()
        print("created: " + (", ".join(str(p) for p in made) if made else "nothing (already set up)"))
    elif args.action == "status":
        print(thread.status())
    elif args.action == "stop":
        thread.stop()
        print(f"stopped: {thread.stop_file}")
    elif args.action == "resume":
        thread.resume()
        print("resumed")
    elif args.action == "ask":
        print(thread.ask(" ".join(args.text)))
    elif args.action == "answer":
        if len(args.text) < 2:
            print("usage: sunmcp thread answer <id> <text>", file=sys.stderr)
            return 2
        thread.answer(args.text[0], " ".join(args.text[1:]))
        print("recorded")
    return 0


async def _run(config_path: str, prompt: str) -> int:
    cfg = load_config(config_path)
    backend = make_backend(cfg.backend)
    async with MCPHub(cfg.servers) as hub:
        attach_vision(hub, Vision(cfg.vision))
        print(await run_turn(backend, hub, [], prompt, cfg.system, on_tool=_print_tool))
    return 0


async def _chat(config_path: str) -> int:
    cfg = load_config(config_path)
    backend = make_backend(cfg.backend)
    history: list = []
    vision = Vision(cfg.vision)
    async with MCPHub(cfg.servers) as hub:
        attach_vision(hub, vision)
        print(f"sunmcp {__version__}: {len(hub.tools)} tools. /screen <question>, /reset, /exit.")
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
            if line.strip().startswith("/screen"):
                if not cfg.vision.enabled:
                    print("ai> vision is disabled in config")
                    continue
                q = line.strip()[len("/screen"):].strip() or None
                try:
                    seen = await vision.look(q)
                except RuntimeError as e:
                    print(f"ai> {e}")
                    continue
                # hand what the vision model saw to the chat model as context
                line = f"[screen, as seen by the vision model]\n{seen}\n\n{q or 'What do you make of this?'}"
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
    s = sub.add_parser("screen", help="screenshot + vision model, answer a question about the screen")
    s.add_argument("question", nargs="?")
    s.add_argument("-m", "--monitor", type=int, default=1)
    s.add_argument("-c", "--config", default="sunmcp.json")
    s = sub.add_parser("init", help="write a sample sunmcp.json")
    s.add_argument("-c", "--config", default="sunmcp.json")
    s = sub.add_parser("box", help="detect this machine, pick models, optionally write sunmcp.json")
    s.add_argument("--write", action="store_true", help="write the config")
    s.add_argument("--force", action="store_true", help="overwrite an existing config")
    s.add_argument("--gpu", action="store_true", help="this machine has a real GPU: let Ollama use it")
    s.add_argument("--install", action="store_true", help="also download and set up the models (needs Ollama)")
    s.add_argument("-c", "--config", default="sunmcp.json")
    s = sub.add_parser("thread", help="a loop that works without commands and never blocks on a question")
    s.add_argument("action", choices=["init", "run", "status", "stop", "resume", "ask", "answer"])
    s.add_argument("text", nargs="*", help="for `answer`: <id> <text>; for `ask`: the question")
    s.add_argument("-d", "--dir", default="thread", help="thread directory (GOAL.md, LOG.md, ...)")
    s.add_argument("-c", "--config", default="sunmcp.json")
    s.add_argument("--interval", type=float, default=900.0, help="seconds between steps (run)")
    s.add_argument("--once", action="store_true", help="do one step and exit (run)")
    s.add_argument("--max-per-day", type=int, default=48, help="step cap per day (run)")
    s.add_argument("--deny", action="append", default=[], help="extra tool-name glob to block (run)")
    s.add_argument("--allow", action="append", default=[], help="tool-name glob exempt from blocking (run)")
    s.add_argument("--notify", help="command that receives each new question as JSON on stdin (run)")
    args = p.parse_args(argv)

    if args.cmd == "thread" and args.action != "run":
        return _thread_control(args)
    if args.cmd == "box":
        hw = detect_hardware()
        tier = choose_tier(hw)
        cpu_only = not args.gpu
        print(report(hw, tier, cpu_only))
        if args.write:
            path = Path(args.config)
            if path.exists() and not args.force:
                print(f"{path} already exists (use --force)", file=sys.stderr)
                return 1
            path.write_text(json.dumps(box_config(tier, cpu_only), indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"wrote {path}")
            if cpu_only:
                for name, text in modelfiles(tier).items():
                    mf = path.parent / f"Modelfile.{name}"
                    mf.write_text(text, encoding="utf-8")
                    print(f"wrote {mf}")
        if args.install:
            if cpu_only and not args.write:
                print("--install needs --write (the Modelfiles must exist first)", file=sys.stderr)
                return 1
            return install_models(tier, cpu_only, cwd=str(Path(args.config).resolve().parent))
        return 0
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
        if args.cmd == "screen":
            return asyncio.run(_screen(args.config, args.question, args.monitor))
        if args.cmd == "thread":
            return asyncio.run(_thread_run(args))
        if args.cmd == "run":
            return asyncio.run(_run(args.config, args.prompt))
        return asyncio.run(_chat(args.config))
    except httpx.ConnectError as e:
        print(f"error: cannot reach the model server: {e}. Is Ollama running?", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
