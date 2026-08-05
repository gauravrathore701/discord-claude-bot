# /caveman command — per-channel level, set from chat

**Date:** 2026-08-04 19:40 IST
**Files:** `bot.py`, `CLAUDE.md`

## Ask

A chat command to set the caveman level (`/caveman ultra` and the other values), with the level
changing **only** when Gaurav sends it — not baked in at deploy time.

## Changes

`load_caveman_prompt()` (single fixed level, built at import) became `caveman_prompt(level)`,
cached per level. `CAVEMAN_LEVEL` from `.env` is now only the fallback default.

- `ChannelState.caveman` — per-channel override, `None` = use the default
- persisted to `.claude/sessions/<channel_id>/caveman.json` via `load_caveman()` / `save_caveman()`,
  loaded in `on_ready` next to the model override
- `run_claude()` resolves `state.caveman or CAVEMAN_LEVEL` per task and appends the matching prompt
- command regex `^[!/]?caveman(?:\s+(\S+))?$` — accepts `/caveman ultra`, `!caveman ultra`,
  `caveman ultra`, case-insensitive. No argument prints the effective level and its source.
- levels: `lite full ultra wenyan-lite wenyan-full wenyan-ultra`, plus `off` (skill not injected,
  plain Claude) and `default` (drop the override)
- `!help` and startup log updated; startup prints the default plus any channel overrides

Set is per channel and survives restarts; it does not touch the other channels.

## Verified

```
py_compile bot.py                 OK
/caveman ultra, !caveman,
caveman wenyan-full, /CAVEMAN Off  all parse, arg extracted
"caveman explain this repo"        NOT a command -> runs as a task
caveman_prompt: ultra 3605 chars, lite 3603, wenyan-full 3617, off 0
persistence round-trip             lite written, re-read as lite, restored to default
live haiku, level=lite             full sentences, no article-dropping
```

Caveat: `wenyan-*` on haiku came back in English — small models ignore the classical-Chinese
instruction. Sonnet/opus honour it better. Not a bot bug; the level does reach the model.

## Not live

Needs `sudo systemctl restart discord-claude` — waiting on Gaurav's yes per the BOT RESTART RULE.
