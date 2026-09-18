# Daily rollover moved 04:45 → 06:30 — 2026-09-17 09:05

- Why: rollover summaries (`fetch_prev_summary`, one `claude --resume` per channel) at 04:45 opened a
  5h usage window 04:30–09:30 that broke the 06:30/11:30/16:30/21:30 grid kept by
  `~/routines/claude_window/window_ping.py`. At 06:30 the calls land on-grid.
- `bot.py`: RESET_HOUR=6, RESET_MINUTE=30 + every "04:45" text (base point `session`, `!session`,
  `!help`, comments). Backup `backups/bot.py.bak2-20260917`. CLAUDE.md, ~/.claude/CLAUDY_REX.md,
  USER.md updated.
- Checked before restart: all channel sessions started after 06:30 today (07:50–08:11), so the new
  cycle start doesn't expire any live session.
- Not live yet — rides the pending restart (checklists + skills index).
