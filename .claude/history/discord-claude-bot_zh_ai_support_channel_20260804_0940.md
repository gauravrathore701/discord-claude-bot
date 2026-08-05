# zh-ai-support channel bound to its folder (obsidian pattern)

**Date:** 2026-08-04 09:40 IST
**Files:** `.claude/channels.json`, `bot.py` (one line), `CLAUDE.md`

## What Gaurav asked for

Channel `1528641869637095444` linked to `/home/gaurav/Projects/zh-ai-support` the same way the
obsidian channel is linked to the vault. Nothing more: no second bot process, no agent-API call,
no webhook wiring, no per-channel jail. His Discord, his access only.

## What ships

### `.claude/channels.json` — one new entry, no new code

```json
{"id": "1528641869637095444", "name": "zh-ai-support",
 "root_dir": "/home/gaurav/Projects/zh-ai-support", "project_routing": false,
 "notes": ["<grounding bullet>", "<the 10 zh-ai-support points>"]}
```

`project_routing: false` -> every message runs in that folder, no `project:` prefix needed.
Base points kept (`replace_points` absent -> `false`), so the channel gets the shared 8 plus
its own 11 = 19 bullets. Resolved block verified with `build_points_block()`.

The points are the same ones as the zh-ai-support agent API's `REMINDER`, copied in as `notes` —
INDEX_NAME/ACCOUNT_ID config files, `.claude/docs` for findings, `.claude/skills` before/after
searches, `config/LOG_INFO.md`, no credentials in chat.

### `bot.py` — one line

```python
if message.author.bot or message.webhook_id:
```

That channel is the zh-ai-support audit-webhook target. `author.bot` is not guaranteed set on
webhook messages, so an audit post could otherwise land as a task (it would be rejected by the
allowlist, but with a reply). Now dropped silently.

### `CLAUDE.md`

Channel documented in the `channels.json` example.

## Not built (deliberately)

First pass added `points_url` / `points_key_env` — points fetched over HTTP from the agent API's
`GET /points` with a disk cache. Gaurav rejected it as overbuilt. All of it removed: the fetcher,
the cache dir, the `ZH_API_KEY` line in `.env`/`.env.example`. `bot.py` is now baseline + the one
webhook line.

The API side keeps `GET /points` and the `webhookLog` field added 2026-08-03; harmless, and
`/points` is still a handy way to read the block.

## Verified before restart

```
py_compile bot.py                    OK
git diff bot.py                      1 line (webhook guard)
zh-ai-support channel resolved       root_dir ok, routing False, replace False, 19 bullets
default channel                      8 bullets   (unchanged)
obsidian channel                     12 bullets  (unchanged)
```

## Live — 2026-08-04 18:00

The Pi rebooted at 12:44; `discord-claude` came up at 12:45 already carrying the new entry
(`Configured channels: [projects, obsidian, zh-ai-support]`). No manual restart was needed.

But `zh-ai-discord` was still enabled and booted alongside it, so **both bots answered every
message in that channel** — Gaurav's screenshot at 17:52 shows two "Claudy Rex APP" replies to
the same message: the old bot's 15s streaming status (`Working... (1m59s)` + `Bash: python3 …`)
next to the new one's `Working in /home/gaurav/Projects/zh-ai-support... (2m00s elapsed)`.
`A query is already running — !cancel to kill it.` is the old bot's string
(`zh-ai-support/discord_bot/bot.py:266`); `Model set to opus.` is this bot's
(`bot.py:603`) — both live, confirming two gateway sessions on one channel.

Fixed: `sudo systemctl disable --now zh-ai-discord` (API idle at the time — `/health` reported
`busy: false` — so no in-flight query was killed).

```
zh-ai-discord    inactive / disabled
discord-claude   active   / enabled
```

One bot on the channel now, no streaming, 120s progress ping, one answer per task.

## Unit deleted — 2026-08-04 18:25

Disabling wasn't enough for Gaurav; he wanted it gone so it can't be re-enabled:

```
sudo rm /etc/systemd/system/zh-ai-discord.service
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

Checked before deleting: the installed unit was byte-identical to
`zh-ai-support/discord_bot/zh-ai-discord.service`, so nothing is lost — reinstalling is a
`cp` + `daemon-reload` + `enable` away if it is ever wanted back.

```
systemctl status zh-ai-discord        Unit zh-ai-discord.service could not be found.
systemctl list-unit-files 'zh-ai*'    zh-ai-api.service   enabled   (only match)
/etc/systemd/system/                  discord-claude, discord-voice, zh-ai-api
discord-claude / discord-voice / zh-ai-api   all active
```

`zh-ai-support/discord_bot/` (bot.py, venv, .env, README, the unit template) left on disk,
unused. Say the word to delete the folder too.
