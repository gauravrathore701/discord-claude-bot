# Deletion rule added to BASE_POINTS — 2026-09-02 08:05

## Ask
Gaurav: every channel must carry a standing point —
always ask before deleting anything, never remove
something just because it looks unnecessary.

## Change
`bot.py` — new `"delete"` key in `BASE_POINTS`,
placed between `restart` and `discord_format`.

Covers: files/dirs, git history (reset --hard, force
push, branch -D), DB rows/tables, systemd units,
config blocks, cron entries, Docker volumes/images,
remote resources.

Requires: state exactly what would go (full paths +
counts), then wait for a clear yes. Back up before
replacing (`file.bak-YYYYMMDD`). Only exception is a
temp file the assistant created in that same task.

## Why BASE_POINTS and not per channel
`build_points_block()` injects every BASE_POINTS entry
into every channel unless that channel sets `omit` or
`replace_points`. Checked `.claude/channels.json` —
projects, obsidian and zh-ai-support all set neither,
so one entry covers all three, plus any channel added
later.

## Verified
```
ast.parse(bot.py)      syntax OK
BASE_POINTS keys       delete present
build_points_block()   bullet renders
```
Backup: `bot.py.bak-20260902`.

## NOT done
Bot not restarted. Per the restart rule that needs an
explicit yes from Gaurav — the rule is on disk but is
NOT live in the running process yet.
