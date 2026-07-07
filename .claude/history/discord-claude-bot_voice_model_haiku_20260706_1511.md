# Voice bot: Claude model switched to Haiku — 2026-07-06 15:11

## What
Set the Rex voice bot's Claude model to **haiku**. It was previously running the
Claude CLI default (no `--model` flag).

## How
`voice_bot.py` already supported an optional `VOICE_MODEL` env var (passed to the
CLI as `--model`), so no code change was needed — just service config:

- Added `Environment=VOICE_MODEL=haiku` to `/etc/systemd/system/discord-voice.service`
- `systemctl daemon-reload && systemctl restart discord-voice`

## Verified
Boot log: `[voice] logged in as Claudy Rex#5707 — whisper=base, model=haiku`
(also visible anytime via the bot's status command — shows `claude model: haiku`).

## Revert
Delete the `Environment=VOICE_MODEL=haiku` line from the unit, daemon-reload, restart.
