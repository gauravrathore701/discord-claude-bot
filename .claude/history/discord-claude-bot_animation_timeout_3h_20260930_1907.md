# animation channel timeout 30m -> 3h

Date: 2026-09-30 19:07 IST

## Change
`.claude/channels.json`, channel `animation`
(id 1549074815783014551):
`"timeout_minutes": 30` -> `"timeout_minutes": 180`
(10800s, resolved by `parse_timeout()` -> `channel_timeout()`
in `run_claude()`'s `asyncio.wait_for`).

Backup: `.claude/channels.json.bak-20260930`
JSON re-validated after edit.

## Not applied yet
`channels.json` is read once at import
(`CHANNELS = load_channels()`, bot.py:272). No reload
command exists, so `systemctl restart discord-claude`
is required. Restart NOT done — awaiting Gaurav's yes.

## Complications reviewed
1. Channel lock — one task per channel; a 3h task
   blocks every other animation message for 3h.
   Only `!cancel` gets out.
2. Daily rollover (06:30) — `do_daily_rollover()`
   returns False while a task runs and retries every
   30s. A task crossing 06:30 delays the animation
   session rotation only; other channels unaffected.
3. Restart/watchdog kills it — `claude` is a child of
   the bot cgroup. Any `systemctl restart`, watchdog
   heartbeat-stale restart, or Pi reboot kills a
   3h task with no resume. 6x longer exposure window.
4. Heartbeat is safe — `heartbeat_loop()` is a
   separate asyncio task; a busy subprocess does not
   starve it. Watchdog won't fire because of the task.
5. Discord chatter — `channel.typing()` re-pings every
   ~5s and `progress_ping` edits every 120s for the
   whole 3h (~90 edits). Under rate limits, but noisy.
6. Conflicts with channel note — animation notes already
   say detach renders over ~5min via
   `systemd-run --user` and never render through MCP.
   Detach+poll survives a bot restart; a 3h blocking
   task does not. The longer timeout is a fallback,
   not a reason to stop detaching.
