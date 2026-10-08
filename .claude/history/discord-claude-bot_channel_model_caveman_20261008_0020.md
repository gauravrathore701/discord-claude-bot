# Channel model / caveman changes

**Date:** 2026-10-08 00:20
**Asked by:** Gaurav

## Changes written to disk
```
rex-chat      opus  -> sonnet
              ultra -> lite
claudy-logs   full  -> ultra
claudy-cmds   full  -> ultra
```

Files, under
`discord-claude-bot/.claude/sessions/<channel-id>/`:
- `1508034882645786644/model.json`
- `1508034882645786644/caveman.json`
- `1537133272319008798/caveman.json`
- `1545758605465100449/caveman.json`

Each one backed up first as `*.bak-20261008`.
Nothing deleted.

## State after the edit
```
id                   model    caveman
1508034842304970772  opus     ultra   rex-code
1508034882645786644  sonnet   lite    rex-chat
1528641869637095444  opus     ultra   zh-ai-support
1537133272319008798  haiku    ultra   claudy-logs
1545733400873271356  opus     off     blog-discussion
1545758605465100449  haiku    ultra   claudy-cmds
1549071536592265266  -        -       rex-finance
1549074815783014551  -        -       rex-animation
1550757911259512842  haiku    -       daily-tasks
```
Blank = no file, falls back to the CLI default
(`~/.claude/settings.json` model `opus`) and to
`CAVEMAN_LEVEL`, which is unset in .env so the code
default `ultra` applies.

## NOT YET LIVE
`bot.py` reads both files only in `on_ready()`
(`load_model` / `load_caveman`), into `STATES` in
memory. The running process still holds the old
values. Takes effect on
`systemctl restart discord-claude` — not done, per
the bot-restart rule; waiting on Gaurav.

Alternative with no restart: run the `/model` and
`/caveman` slash commands inside each channel. Those
write the same files AND update the live state.
