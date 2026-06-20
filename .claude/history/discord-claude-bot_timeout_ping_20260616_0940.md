# discord-claude-bot — Timeout Increase & Progress Ping
**Date:** 2026-06-16 09:40 IST

## Problem
Tasks timing out at 600s ("Timed out after 600s"). Complex tasks (many tool calls, deep file searches) regularly exceed 10 minutes.

## Changes to bot.py

### 1. Timeout increased: 600s → 1200s
```python
TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "1200"))
```
20 minutes is the new default. Still configurable via `TASK_TIMEOUT` env var.

### 2. Progress ping (every 2 minutes)
New `progress_ping()` coroutine edits the "Working in `...`" status message every 120s to show elapsed time:
> Working in `/home/gaurav/Projects`... (2m00s elapsed)

Runs as a parallel asyncio task, cancelled when the main task finishes or is cancelled.

```python
PING_INTERVAL = 120

async def progress_ping(status_msg, cwd):
    start = time.time()
    while True:
        await asyncio.sleep(PING_INTERVAL)
        elapsed = int(time.time() - start)
        m, s = divmod(elapsed, 60)
        await status_msg.edit(content=f"Working in `{cwd}`... ({m}m{s:02d}s elapsed)")
```

## Service
Restarted and confirmed active since 09:37:47 IST, online as Claudy Rex#5707.
