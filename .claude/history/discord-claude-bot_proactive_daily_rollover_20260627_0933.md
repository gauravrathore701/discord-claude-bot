# discord-claude-bot — Proactive Daily Session Rollover
**Date:** 2026-06-27 09:33

## Problem
Sessions reset daily at 04:45, and the bot already bridged context across the
reset — but only *lazily*: `fetch_prev_summary()` ran inside `run_claude()` on
whatever message happened to arrive first after 04:45, adding latency to that
reply and depending on a message actually showing up.

## Changes to bot.py
- Added `daily_rollover_loop()` — background asyncio task started in
  `on_ready()`, sleeps until the next 04:45 and fires `do_daily_rollover()`.
- `do_daily_rollover()` summarizes the expiring session via the existing
  `fetch_prev_summary()`, caches it to `.claude/sessions/prev_summary.json`,
  rotates `_session_id` → `_prev_session_id`, and clears current session
  state. If a task is mid-flight at 04:45 it skips and retries every 30s
  rather than waiting for the next day's window.
- `run_claude()` now reads the cached summary first; only falls back to the
  old lazy fetch if the bot was offline when rollover should have run.

## Security fix
`.claude/sessions/chat_history.json` and `model.json` were git-tracked
(not gitignored) despite chat history potentially containing anything a
user pastes in Discord — currently it held a leaked GitHub PAT from earlier
today's conversation. Untracked both with `git rm --cached` (kept on disk)
and added `chat_history.json`, `model.json`, `prev_summary.json` to
`.claude/sessions/.gitignore`.

## Not yet done
- Committed locally on `develop`, not pushed — confirm before pushing.
- Bot service not yet restarted to pick up the change.
