# Slack relay: every answer, Block Kit formatting — 2026-09-19 18:50

Gaurav wants to read zh-ai-support from Slack on the office laptop, so
the mirror is no longer webhook-only and the payload is formatted.

## Changes in bot.py
- **Gate dropped.** `if is_webhook: await relay_to_slack(...)` at the two
  call sites (success + cancelled) is now unconditional. New
  `slack_source` holds the Discord display name — the webhook's name for
  webhook posts, Gaurav's for typed ones — and is passed as the new
  `source` arg so Slack shows who asked.
- **`to_slack_mrkdwn()`** — Slack mrkdwn is not Discord markdown.
  `**bold**` -> `*bold*`, `__u__` -> `_u_`, `~~s~~` -> `~s~`,
  `## head` -> `*head*`, `[t](u)` -> `<u|t>`, `-`/`*`/`+` bullets -> `•`.
  Splits on ``` first and leaves fenced code untouched. The heading regex
  uses `[ \t]*$`, not `\s*$` — greedy `\s*` ate the blank line after
  every heading and glued paragraphs together.
- **`chunk_for_slack()`** — cuts on line boundaries at 2900 chars
  (Slack's section limit is 3000), closing and reopening a fence that
  straddles a cut. Same idea as `split_for_discord()`.
- **`relay_to_slack()`** now builds Block Kit: `header` = channel name,
  `context` = who + `19 Sep 2026, 18:50 IST`, a block-quoted
  `:grey_question: *Question*` section, a `divider`, then
  `:speech_balloon: *Answer*` across as many sections as needed. Keeps a
  `text` fallback so the Slack notification and any non-block client
  still read. Caps: query 1500, answer 9000, blocks 50; anything cut
  gets a `truncated — full text is in Discord` context line.

## Verified
- `py_compile` clean.
- `to_slack_mrkdwn` checked against a sample with a heading, bold, a
  link, strikethrough, bullets and a bash fence — all converted, fence
  untouched, blank lines preserved.
- Payload dry-run through a fake aiohttp session: 5 blocks, correct
  shape. **Nothing was posted to Slack.**

## Backups
- `backups/bot.py.bak-slackrelay-20260919`
- `backups/CLAUDE.md.bak-slackrelay-20260919`

## Scope note
Only channels with `slack_webhook_env` relay, and zh-ai-support is the
only one that has it — no other channel's traffic goes to Slack.
`!` commands return before `do_task()`, so they are not mirrored either.

## Pending
Bot restart (asked, not yet done). Whether that webhook points at the
office workspace or a personal one is still unconfirmed — worth knowing,
since every typed message now lands there.
