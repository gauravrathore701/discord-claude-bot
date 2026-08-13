# Webhook-triggered tasks (zh-ai-support) — 2026-08-12 22:15

Gaurav wants an external system to POST to the zh-ai-support channel webhook and
have the bot answer that query in-channel, instead of the post being ignored.

Before this change `on_message` dropped every webhook post outright
(`if message.author.bot or message.webhook_id: return`) to stop the audit-log
webhook from triggering tasks.

## Changes (`bot.py`)

**`ChannelConfig`** — two new fields:
- `webhooks: set[int]` — webhook IDs allowed to run tasks in that channel
- `webhooks_any: bool` — set when the config lists `"any"` / `"*"`

**`load_channels()`** — parses `"webhooks"` from `channels.json`; accepts a single
value or a list, numeric entries become IDs, `any`/`*` sets `webhooks_any`.

**`on_message` gate** — replaced the blanket webhook drop:
- webhook post + ID allowed for this channel -> runs as a task
- webhook post otherwise -> silently ignored, same as before
- non-webhook bot message -> ignored (this is what stops reply loops; the bot's
  own messages have no `webhook_id`)
- human -> unchanged `ALLOWED_IDS` check

**Webhook callers are questions-only** — a post matching `^[!/]` or
`(model|caveman) <known-value>` is refused, so an unattended caller cannot run
`!cancel`, `!newsession` or switch model/caveman level.

**Ack + provenance** — an accepted webhook post gets an 👀 reaction and the status
reply reads `Ack — webhook request received. Working in <cwd>...`. The prompt is
prefixed with a line telling Claude the request came through the webhook (with the
webhook's display name) and is not typed by Gaurav.

## Config (`.claude/channels.json`)

`zh-ai-support` entry gained:

```json
"webhooks": ["1537137799050956923"]
```

That is the ID segment of the webhook URL only — the URL's token is **not** stored
in the repo, and is not needed: the bot identifies the caller by ID on inbound
messages. Backup of the previous file: `.claude/channels.json.bak.20260812`.

## Verification

- `ast.parse` clean; module imports with real `.env`.
- `CHANNELS` loads `zh-ai-support hooks={1537137799050956923}`, other channels
  empty (`any=False`), so behaviour elsewhere is unchanged.
- Command guard checked: `!cancel`, `/caveman ultra`, `model opus` blocked;
  `caveman rules`, `why is agent_api down?`, `check index config` pass as tasks.

Not yet live — needs `systemctl restart discord-claude`, pending Gaurav's yes.
