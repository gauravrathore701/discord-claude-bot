# Live step status via stream-json — PARTIAL, needs finishing — 2026-10-13 22:10

## Goal
Replace the "Working in `<cwd>`... (Xm elapsed)" status line with a live,
rolling view of what Claude is doing (tool calls, short text, thinking),
like the desktop app. Discord can't stream; the bot edits one status
message every few seconds instead.

## State of bot.py right now
Backup of the untouched original: `bot.py.bak-20261013-stream`.
The running bot still uses the old code (loaded in memory). **bot.py on
disk does not run as-is** — a restart now fails on the first task.

Done:
- Constants near the top: `PING_INTERVAL = 30`, `STEP_INTERVAL = 3`,
  `STEP_LINES = 6`, `STEP_WIDTH = 70`.
- `run_claude()`: CLI now called with `--output-format stream-json --verbose`.
  Subprocess created with `limit=32 MiB` (a single event line can hold a
  whole tool result). stderr is drained in a background task. A `pump()`
  coroutine reads stdout line by line: the `type == "result"` event is kept
  as `result`; every other event goes through `describe_event(ev)` and is
  appended to `state.steps`; non-JSON lines are collected in `junk` as the
  fallback output. Timeout / kill / `state.active_proc` handling unchanged.
  Session id, `is_error` and `result` are read from the result event exactly
  as the old json mode did.

Not done:
1. `ChannelState` (dataclass, ~line 247): add `steps: list` with
   `field(default_factory=list)`. `run_claude` sets `state.steps = []` per
   task, but `progress_ping` may read it before that.
2. `describe_event(ev) -> list[str]`, defined above `run_claude`:
   - return [] unless `ev.get("type") == "assistant"`
   - for each item in `ev["message"]["content"]`:
     - `tool_use` -> `"<name>: <what>"`, `<what>` = first present of
       `input.description`, basename of `input.file_path`, `input.pattern`,
       `input.command`
     - `text` -> `"💬 " + text`
     - `thinking` -> `"💭 " + thinking`
   - collapse whitespace to single spaces, cut to `STEP_WIDTH`
3. `progress_ping(status_msg, state)` replaces `progress_ping(status_msg, cwd)`:
   - every `STEP_INTERVAL` s; edit only if `len(state.steps)` changed or
     `PING_INTERVAL` s passed since the last edit
   - content: `⏳ {m}m{s:02d}s` then the last `STEP_LINES` steps, one per
     line, each passed through `discord.utils.escape_markdown`
   - keep the existing `except (asyncio.CancelledError, discord.NotFound,
     discord.HTTPException): pass`
   - the one caller in `do_task` (`grep -n progress_ping bot.py`) passes
     `state` instead of `cwd`

## Verify
- `venv/bin/python -m py_compile bot.py`
- Feed `/tmp/sj_test.jsonl` (sample stream from one real CLI run) through
  `describe_event`; expect `Bash: Print hi` and `💬 done`.
- Event shape confirmed on this CLI: system/init, assistant(tool_use),
  rate_limit_event, user(tool_result), assistant(text), result
  (`subtype`, `is_error`, `session_id`, `result`).

## Restart
Only after Gaurav's yes. Use the `restart-own-service` skill (delayed
`systemd-run`) so the reply isn't killed with the service.

## Rollback
`cp bot.py.bak-20261013-stream bot.py` then restart the same way.

## Also update
CLAUDE.md "Task execution" bullet: mention stream-json + live steps.

## Finished 22:16
- Missing pieces added by Gaurav's SSH Claude session (steps field, describe_event, progress_ping(status, state)); verified by Rex: py_compile OK, pieces at :249/:701/:826, caller passes state.
- Rex added `state.steps = []` in do_task before the ping starts (no flash of previous task's steps).
- Restart queued via systemd-run +15s after Gaurav's "fix + restart".

## Follow-up 22:25 (NOT restarted — Gaurav checks tomorrow)
- Initial status text: `Working in <cwd>...` -> `⏳ thinking…` (webhook keeps its "Ack — webhook request received." prefix).
- describe_event: empty thinking blocks skipped. Checked transcripts: all 67 thinking blocks in the latest session have empty `thinking` text — this CLI omits it, so 💭 lines only appear if a future CLI/setting sends the text.
- Live after next restart (06:30 rollover does NOT restart the service; needs a manual restart).
