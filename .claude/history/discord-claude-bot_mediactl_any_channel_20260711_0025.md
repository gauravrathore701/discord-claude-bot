# mediactl — natural-language monitor control from any channel (2026-07-11 00:25)

## Ask
Make monitor/YouTube control work from ANY Discord channel via rough natural
language, not just exact `!video` commands in one channel. MCP-like: rough
prompt → Claude interprets → executes.

## Problem
`!play`/`!video` are handled in `bot.py:on_message` BEFORE reaching the Claude
subprocess. Claude (the per-channel subprocess) had no way to trigger media —
it could only tell the user to type the raw command.

## Solution — standalone `mediactl.py` CLI
The bot keeps a cage + Chromium kiosk alive permanently (media.py v4). A separate
process can drive that same Chromium over CDP (port 9222) and cage's Wayland
socket (wlr-randr) — both cross-process. So `mediactl.py` needs NO bot IPC.

- **New file `mediactl.py`** — stdlib-only (no venv/aiohttp), hand-rolled CDP
  websocket client. Commands: `play`, `video`, `stop`, `pause`, `resume`,
  `fullscreen`, `wake`, `sleep`, `status`. Prints one JSON line. Mirrors
  media.py behaviour (ad-filtered search, fullscreen on video, clock on stop).
- **bot.py** — added a MONITOR/YOUTUBE CONTROL bullet to the GLOBAL
  IMPORTANT-POINTS block (injected into every channel's prompt). Tells Claude to
  translate plain-language screen requests and run `mediactl.py <cmd>`, with
  mapping examples. Now works from any channel, any phrasing.

## Also shipped this session (earlier tasks, same media stack)
- media.py v4: flip clock idle screen (`static/flipclock.html`), cage starts at
  bot startup (`MEDIA.startup()` in on_ready), `stop`/idle navigate back to clock
  instead of killing cage.
- Fullscreen: `JS_FULLSCREEN` + `_eval(user_gesture=True)`, auto-triggered after
  `!video` playback starts.
- `--password-store=basic` (keyring dialog fix).

## Verify
`python3 mediactl.py status` → `{"ok": true, ..., "hdmi": "HDMI-A-2"}`. Bot active.

## Note
mediactl assumes the bot's cage/Chromium is alive (it is, persistently). If CDP
is down it returns `{"ok": false, "error": "kiosk/CDP not up ..."}` rather than
starting cage itself — cage lifecycle stays owned by the bot.
