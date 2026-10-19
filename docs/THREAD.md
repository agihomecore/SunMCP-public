# The thread (five years, moving)

Point zero of the family. One continuous thread of work, not a pile of sessions.

## Rules
1. A rolling five-year horizon: today, this week, this quarter, this year, five years. Each step moves the window forward.
2. The thread lives in plain files (ERA: CENTURY/YEAR/MONTH/WEEK/DAY/HOUR, each with SHORT/MEDIUM/LONG/HANDOFF/CURRENT/LOG). Whoever wakes up reads HANDOFF and CURRENT first.
3. Work without commands. Questions are posted (Telegram) and the work continues on the best reading; the answer, when it comes, corrects course. Nothing blocks on a question.
4. Irreversible actions are the exception: prepare, state the decision, stop.
5. Everything the thread learns is written down before the session ends.

## What SunMCP needs for this (not built yet)
- `sunmcp thread`: a loop that reads the goal file, picks the next step, runs it with tools, appends to the LOG.
- A non-blocking `ask` tool: sends the question to the allow-listed Telegram chat and returns immediately.
- A scheduler (OS task or Pro daemon) to wake the loop; a kill switch file.
