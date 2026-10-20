"""The thread: a loop that works without commands and never blocks on a question.

Everything the thread knows lives in plain files inside one directory:

  GOAL.md        what the owner wants (the owner edits this)
  LOG.md         what the thread did, appended after every step
  OUTBOX.jsonl   questions the thread asked (delivered by --notify, or by the Pro Telegram bridge)
  ANSWERS.jsonl  the owner's answers (`sunmcp thread answer <id> "text"`)
  STATE.json     bookkeeping (how many answers were already shown to the model)
  STOP           kill switch: while this file exists the thread does nothing

Rules, in code:
  * `ask` returns at once. The model continues on its stated assumption; the answer, when it
    arrives, is shown at the start of a later step and corrects course.
  * Tools that look irreversible (delete, send, publish, push, pay ...) are blocked. The attempt
    is turned into an approval question in the outbox: prepare, state the decision, stop.
  * Every step starts from the files, not from chat history, so it survives restarts.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .agent import run_turn
from .hub import MCPHub
from .llm import Backend

GOAL_TEMPLATE = """# Goal

Write here what the thread should move forward. One paragraph is enough.

# Horizon
- today:
- this week:
- this quarter:
- five years:

# Boundaries
- Irreversible actions (delete, send, publish, push, pay) need my answer first.
"""

# Names (lowercase glob) that look irreversible. `--allow` overrides, `--deny` extends.
DEFAULT_DENY = (
    "*delete*", "*remove*", "*send*", "*publish*", "*push*", "*pay*", "*purchase*",
    "*transfer*", "*drop*", "*format*", "kill*", "*_kill*", "*trash*", "*post_*",
)
ALWAYS_ALLOWED = ("ask", "thread_log")

RULES = """You are the thread: one continuous line of work that moves without being told.
Do exactly ONE useful next step toward the goal, using your tools.
- Never wait for the owner. If you need a decision, call `ask` with your best assumption and keep going on it.
- Irreversible actions (delete, send, publish, push, pay) are blocked. Prepare everything, call `ask`, stop.
- When the step is done, finish with a short plain-text summary: what you did, what is next.
- If there is nothing useful to do right now, say so in one line."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Thread:
    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)
        self.goal_file = self.dir / "GOAL.md"
        self.log_file = self.dir / "LOG.md"
        self.outbox = self.dir / "OUTBOX.jsonl"
        self.answers = self.dir / "ANSWERS.jsonl"
        self.state_file = self.dir / "STATE.json"
        self.stop_file = self.dir / "STOP"

    # -- setup / control ------------------------------------------------------
    def init(self) -> list[Path]:
        self.dir.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []
        if not self.goal_file.exists():
            self.goal_file.write_text(GOAL_TEMPLATE, encoding="utf-8")
            created.append(self.goal_file)
        if not self.log_file.exists():
            self.log_file.write_text("# Thread log\n", encoding="utf-8")
            created.append(self.log_file)
        return created

    def stopped(self) -> bool:
        return self.stop_file.exists()

    def stop(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stop_file.write_text(_now() + "\n", encoding="utf-8")

    def resume(self) -> None:
        self.stop_file.unlink(missing_ok=True)

    # -- files ----------------------------------------------------------------
    def goal(self) -> str:
        if not self.goal_file.exists():
            raise FileNotFoundError(f"{self.goal_file} not found; run `sunmcp thread init`")
        return self.goal_file.read_text(encoding="utf-8-sig").strip()

    def log(self, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(f"\n## {_now()}\n{text.strip()}\n")

    def recent_log(self, chars: int = 3000) -> str:
        if not self.log_file.exists():
            return ""
        text = self.log_file.read_text(encoding="utf-8-sig")
        return text[-chars:]

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue  # a half-written line must not kill the thread
        return rows

    def _append_jsonl(self, path: Path, row: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def questions(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.outbox)

    def ask(self, question: str, assumption: str = "") -> str:
        qid = f"q{len(self.questions()) + 1}"
        self._append_jsonl(
            self.outbox, {"id": qid, "ts": _now(), "question": question, "assumption": assumption}
        )
        return qid

    def answer(self, qid: str, text: str) -> None:
        self._append_jsonl(self.answers, {"id": qid, "ts": _now(), "answer": text})

    def _state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def take_new_answers(self) -> list[dict[str, Any]]:
        """Answers not yet shown to the model; marks them as shown."""
        rows = self._read_jsonl(self.answers)
        state = self._state()
        seen = int(state.get("answers_seen", 0))
        fresh = rows[seen:]
        if fresh:
            state["answers_seen"] = len(rows)
            self.state_file.write_text(json.dumps(state), encoding="utf-8")
        return fresh

    def status(self) -> str:
        qs, ans = self.questions(), self._read_jsonl(self.answers)
        answered = {a.get("id") for a in ans}
        open_q = [q for q in qs if q["id"] not in answered]
        lines = [
            f"thread dir : {self.dir}",
            f"state      : {'STOPPED (STOP file present)' if self.stopped() else 'running allowed'}",
            f"questions  : {len(qs)} asked, {len(open_q)} unanswered",
        ]
        for q in open_q[-5:]:
            lines.append(f"  {q['id']}: {q['question']}")
        return "\n".join(lines)


def is_blocked(name: str, deny: tuple[str, ...], allow: tuple[str, ...] = ()) -> bool:
    n = name.lower()
    if n in ALWAYS_ALLOWED:
        return False
    if any(fnmatch(n, pat.lower()) for pat in allow):
        return False
    return any(fnmatch(n, pat.lower()) for pat in deny)


class GuardedHub:
    """Wraps a hub: kill switch before every call, irreversible-looking tools turned into questions."""

    def __init__(
        self,
        hub: MCPHub,
        thread: Thread,
        deny: tuple[str, ...] = DEFAULT_DENY,
        allow: tuple[str, ...] = (),
    ) -> None:
        self._hub, self._thread, self._deny, self._allow = hub, thread, deny, allow

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self._hub.tools

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        if self._thread.stopped():
            return "STOP file present: the owner stopped the thread. Finish with a short summary.", True
        if is_blocked(name, self._deny, self._allow):
            qid = self._thread.ask(
                f"Approval needed: {name}({json.dumps(arguments, ensure_ascii=False)[:300]})",
                "not done; waiting for the owner",
            )
            return (
                f"BLOCKED by thread policy (looks irreversible). Queued as {qid} for the owner. "
                "Prepare everything else and stop here.",
                True,
            )
        return await self._hub.call(name, arguments)


def attach_thread_tools(hub: MCPHub, thread: Thread, notify: Callable[[dict[str, Any]], None] | None = None) -> None:
    if any(spec["name"] == "ask" for spec in hub.tools):
        return  # already attached (the loop calls this every step)
    async def ask(args: dict[str, Any]) -> tuple[str, bool]:
        question = str(args.get("question") or "").strip()
        if not question:
            return "question is empty", True
        qid = thread.ask(question, str(args.get("assumption") or ""))
        if notify:
            notify({"id": qid, "question": question, "assumption": args.get("assumption") or ""})
        return f"Queued as {qid}. Do NOT wait: continue on your assumption. The answer will arrive in a later step.", False

    async def thread_log(args: dict[str, Any]) -> tuple[str, bool]:
        entry = str(args.get("entry") or "").strip()
        if not entry:
            return "entry is empty", True
        thread.log(entry)
        return "logged", False

    hub.register_builtin(
        {
            "name": "ask",
            "description": (
                "Ask the owner a question WITHOUT waiting. Returns immediately. State your best assumption; "
                "keep working on it. Use for decisions, approvals, and missing facts."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "assumption": {"type": "string", "description": "What you will do meanwhile."},
                },
                "required": ["question"],
            },
        },
        ask,
    )
    hub.register_builtin(
        {
            "name": "thread_log",
            "description": "Append a note to the thread log (decisions, findings, what is next).",
            "input_schema": {
                "type": "object",
                "properties": {"entry": {"type": "string"}},
                "required": ["entry"],
            },
        },
        thread_log,
    )


def step_prompt(thread: Thread) -> str:
    parts = [RULES, "", "## GOAL", thread.goal()]
    log = thread.recent_log()
    if log.strip():
        parts += ["", "## RECENT LOG", log]
    fresh = thread.take_new_answers()
    if fresh:
        parts += ["", "## NEW ANSWERS FROM THE OWNER (apply them, they correct your course)"]
        parts += [f"- {a.get('id')}: {a.get('answer')}" for a in fresh]
    return "\n".join(parts)


async def run_step(
    backend: Backend,
    hub: MCPHub,
    thread: Thread,
    system: str | None = None,
    deny: tuple[str, ...] = DEFAULT_DENY,
    allow: tuple[str, ...] = (),
    notify: Callable[[dict[str, Any]], None] | None = None,
    on_tool: Any = None,
) -> str:
    attach_thread_tools(hub, thread, notify)
    guarded = GuardedHub(hub, thread, deny, allow)
    prompt = step_prompt(thread)
    result = await run_turn(backend, guarded, [], prompt, system, on_tool=on_tool)  # type: ignore[arg-type]
    thread.log(result)
    return result


def shell_notifier(command: str) -> Callable[[dict[str, Any]], None]:
    """Run `command` with the question as JSON on stdin (for example a script that posts to Telegram)."""

    def notify(q: dict[str, Any]) -> None:
        try:
            subprocess.run(
                command, input=json.dumps(q, ensure_ascii=False), text=True, shell=True,
                timeout=30, check=False, capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as e:
            print(f"notify failed: {e}", file=sys.stderr)

    return notify


async def run_loop(
    backend: Backend,
    hub: MCPHub,
    thread: Thread,
    system: str | None = None,
    interval: float = 900.0,
    once: bool = False,
    max_per_day: int = 48,
    deny: tuple[str, ...] = DEFAULT_DENY,
    allow: tuple[str, ...] = (),
    notify: Callable[[dict[str, Any]], None] | None = None,
    on_tool: Any = None,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> int:
    """Run steps until STOP appears. Returns the number of steps taken."""
    steps, day, today_count, delay = 0, time.strftime("%Y-%m-%d"), 0, interval
    while not thread.stopped():
        if time.strftime("%Y-%m-%d") != day:
            day, today_count = time.strftime("%Y-%m-%d"), 0
        if today_count >= max_per_day:
            thread.log(f"daily cap of {max_per_day} steps reached; sleeping until tomorrow")
            await sleep(min(interval, 3600))
            continue
        try:
            await run_step(backend, hub, thread, system, deny, allow, notify, on_tool)
            delay = interval
        except FileNotFoundError:
            raise
        except Exception as e:  # a failed step must not end the thread; back off and retry
            thread.log(f"step failed: {e!r}")
            delay = min(delay * 2, 6 * 3600)
        steps += 1
        today_count += 1
        if once or thread.stopped():
            break
        await sleep(delay)
    return steps
