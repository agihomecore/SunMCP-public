import json

import pytest

from sunmcp import MCPHub, ToolCall, Turn
from sunmcp.thread import DEFAULT_DENY, Thread, is_blocked, run_loop, run_step


class Scripted:
    """Backend that replays scripted turns and records what the model was shown."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    async def complete(self, messages, tools, system=None):
        self.seen.append(messages[0]["content"])
        return self.turns.pop(0) if self.turns else Turn(content="nothing to do")


def _thread(tmp_path):
    t = Thread(tmp_path / "thread")
    t.init()
    return t


def test_init_is_idempotent(tmp_path):
    t = Thread(tmp_path / "t")
    assert len(t.init()) == 2
    assert t.init() == []


def test_blocked_patterns():
    assert is_blocked("gmail__send_message", DEFAULT_DENY)
    assert is_blocked("fs__delete_file", DEFAULT_DENY)
    assert not is_blocked("fs__read_file", DEFAULT_DENY)
    assert not is_blocked("ask", DEFAULT_DENY)
    assert not is_blocked("skills__list", DEFAULT_DENY)  # 'kill' inside 'skills' must not trip
    assert not is_blocked("gmail__send_message", DEFAULT_DENY, allow=("gmail__send*",))


async def test_ask_does_not_block_and_log_is_written(tmp_path):
    t = _thread(tmp_path)
    backend = Scripted(
        [
            Turn(tool_calls=[ToolCall("1", "ask", {"question": "Which disk first?", "assumption": "the 12 TB"})]),
            Turn(content="Chose the 12 TB, asked the owner."),
        ]
    )
    async with MCPHub({}) as hub:
        out = await run_step(backend, hub, t)
    assert "12 TB" in out
    q = t.questions()
    assert q[0]["id"] == "q1" and q[0]["assumption"] == "the 12 TB"
    assert "Chose the 12 TB" in t.log_file.read_text(encoding="utf-8")


async def test_answers_reach_the_next_step_once(tmp_path):
    t = _thread(tmp_path)
    t.answer("q1", "take the 12 TB")
    backend = Scripted([Turn(content="ok"), Turn(content="ok again")])
    async with MCPHub({}) as hub:
        await run_step(backend, hub, t)
        await run_step(backend, hub, t)
    assert "take the 12 TB" in backend.seen[0]
    assert "take the 12 TB" not in backend.seen[1]


async def test_irreversible_tool_is_blocked_and_becomes_a_question(tmp_path):
    t = _thread(tmp_path)
    ran = []

    async def handler(args):
        ran.append(args)
        return "sent", False

    backend = Scripted(
        [Turn(tool_calls=[ToolCall("1", "send_email", {"to": "x@y.z"})]), Turn(content="prepared, waiting")]
    )
    async with MCPHub({}) as hub:
        hub.register_builtin({"name": "send_email", "description": "", "input_schema": {"type": "object"}}, handler)
        await run_step(backend, hub, t)
    assert ran == []
    assert "Approval needed: send_email" in t.questions()[0]["question"]


async def test_stop_file_ends_the_loop(tmp_path):
    t = _thread(tmp_path)
    backend = Scripted([])
    calls = []

    async def fake_sleep(sec):
        calls.append(sec)
        t.stop()  # the owner stops it during the pause

    async with MCPHub({}) as hub:
        steps = await run_loop(backend, hub, t, interval=5, sleep=fake_sleep)
    assert steps == 1 and calls == [5]


async def test_failed_step_is_logged_and_loop_survives(tmp_path):
    t = _thread(tmp_path)

    class Boom:
        n = 0

        async def complete(self, messages, tools, system=None):
            Boom.n += 1
            if Boom.n == 1:
                raise RuntimeError("model down")
            return Turn(content="back")

    sleeps = []

    async def fake_sleep(sec):
        sleeps.append(sec)
        if len(sleeps) == 2:
            t.stop()

    async with MCPHub({}) as hub:
        steps = await run_loop(Boom(), hub, t, interval=10, sleep=fake_sleep)
    assert steps == 2
    assert sleeps == [20, 10]  # backed off after the failure, reset after success
    assert "step failed" in t.log_file.read_text(encoding="utf-8")


def test_missing_goal_is_a_readable_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        Thread(tmp_path / "none").goal()


def test_half_written_outbox_line_is_skipped(tmp_path):
    t = _thread(tmp_path)
    t.outbox.write_text('{"id": "q1", "question": "a"}\n{"id": "q2", "ques', encoding="utf-8")
    assert [q["id"] for q in t.questions()] == ["q1"]
    assert json.loads(t.outbox.read_text().splitlines()[0])["question"] == "a"
