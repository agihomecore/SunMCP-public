# The thread (five years, moving)

Point zero of the family. One continuous thread of work, not a pile of sessions.

## Rules
1. A rolling five-year horizon: today, this week, this quarter, this year, five years. Each step moves the window forward.
2. The thread lives in plain files (ERA: CENTURY/YEAR/MONTH/WEEK/DAY/HOUR, each with SHORT/MEDIUM/LONG/HANDOFF/CURRENT/LOG). Whoever wakes up reads HANDOFF and CURRENT first.
3. Work without commands. Questions are posted (Telegram) and the work continues on the best reading; the answer, when it comes, corrects course. Nothing blocks on a question.
4. Irreversible actions are the exception: prepare, state the decision, stop.
5. Everything the thread learns is written down before the session ends.

## What SunMCP has (v0.2.7)
- `sunmcp thread init | run | status | answer | ask | stop | resume` (src/sunmcp/thread.py).
- Non-blocking `ask` tool and `thread_log` tool, built in.
- Irreversible-looking tool names are blocked and queued as approval questions (default globs in `DEFAULT_DENY`; `--allow`, `--deny`).
- `STOP` file kill switch, daily step cap, backoff after failures, half-written JSONL lines tolerated.
- `--notify "<command>"`: each new question is piped to the command as JSON.

## Not built yet
- Telegram delivery of OUTBOX and answering by reply (planned in the Pro bridge).
- Scheduler install helper (Windows Task Scheduler / systemd timer). For now run `sunmcp thread run` under either.
- Reading the ERA folder layout directly (today GOAL.md is a plain file you or ERA tooling keep up to date).
