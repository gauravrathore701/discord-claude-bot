# Slack relay for webhook-sourced answers — 2026-08-12 22:30

Follow-up to `discord-claude-bot_webhook_triggered_tasks_20260812_2215.md`.
Gaurav wants: query arrives on the zh-ai-support Discord webhook -> bot answers in
Discord -> the original query **and** the answer are pushed to a Slack incoming
webhook.

## Changes (`bot.py`)

- `import aiohttp` (already a discord.py dependency, 3.13.5 in `venv/`).
- `ChannelConfig.slack_webhook: str | None` — resolved in `load_channels()` from
  `os.environ[entry["slack_webhook_env"]]`. `channels.json` stores only the **name**
  of the env var, so the tokened Slack URL never enters the repo.
- `relay_to_slack(cfg, query, answer)` — POSTs
  `{"text": "*Query* (via `<channel>` Discord webhook)\n…\n\n*Answer*\n…"}`,
  20s timeout, query clipped to 1500 chars and answer to 2500 (`… (truncated)`
  marker). Wrapped in a blanket `except` and only prints to the journal: the
  Discord answer is already delivered by then, so a Slack failure must not surface
  as a task error.
- `do_task()` calls it after `send_long()` for webhook-sourced messages only, and
  also on the cancelled path with `(task was cancelled before it finished)` so the
  Slack side never waits on an answer that will not come. Messages typed by Gaurav
  are never relayed.

## Config

- `.env` (gitignored): `ZH_SLACK_WEBHOOK_URL=…` — value not reproduced here.
- `.env.example`: empty `ZH_SLACK_WEBHOOK_URL=` placeholder.
- `.claude/channels.json`, zh-ai-support entry: `"slack_webhook_env": "ZH_SLACK_WEBHOOK_URL"`.

## Verification

- Module imports with the real `.env`; `zh-ai-support` resolves both
  `webhooks={1537…923}` and a non-empty `slack_webhook`; other channels resolve
  neither.
- Live test post through `relay_to_slack()` returned HTTP 2xx —
  journal line `slack relay ok (zh-ai-support)`. A test Q&A pair is visible in the
  Slack channel.

Not yet live in the running bot — still needs `systemctl restart discord-claude`,
pending Gaurav's confirmation (same restart as the webhook-trigger change).
