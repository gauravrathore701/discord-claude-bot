# zh-ai-support channel — IST timezone point

Date: 2026-08-21

## What
Added one bullet to the `zh-ai-support` channel `notes` in
`/home/gaurav/Projects/discord-claude-bot/.claude/channels.json`
(channel id `1528641869637095444`).

Text:
> TIMEZONE — I am in IST (Asia/Kolkata, UTC+05:30). Read every time I
> give ("since 3pm", "yesterday 10:30", "today") as IST, and report every
> time back in IST. ES @timestamp is UTC, so convert: pass +05:30 offsets
> in absolute queries and label output times IST, never raw UTC.

## Why
Gaurav is in IST; log windows and answers were ambiguous vs the UTC ES
cluster.

## Effect
`build_points_block(cfg)` appends channel `notes` to IMPORTANT POINTS TO
REMEMBER, so the bullet is injected into every prompt in that channel
only. Verify in-channel with `!points`.

## Rollout
`CHANNELS = load_channels()` runs at import (bot.py:241) — needs
`sudo systemctl restart discord-claude` to take effect.
Backup of pre-edit file: /tmp/channels.json.bak
