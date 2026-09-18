# Interactive checklists + daily task list — 2026-09-17 08:30

Asked in #rex-chat (08:15, buttons option picked) → built in #rex-code.

## What
- New `checklist.py`: tap-to-tick button messages (discord.py 2.7.1 `DynamicItem`,
  custom_id `ck:<key>:<line>:<hash8>`, survive restarts).
- Source of truth = markdown `- [ ]` files:
  - Daily: vault `Mobile/Tasks/YYYY-MM-DD.md`, built from `Recurring.md` + yesterday's
    unticked one-offs; posted to #rex-chat (`TASKS_CHANNEL_ID`) at `TASKS_POST_TIME` 07:00,
    or at startup if missed.
  - Ad-hoc: Claude emits a ```checklist block → `.claude/checklists/<key>.md`.
- `watch_loop()` (15s) re-renders a message when its file mtime changes (Claude/Obsidian edits).
- Commands: `!tasks`, `!task add <text>`, `!task rm <n>` (native, no Claude call, not for webhooks).
- New `BASE_POINTS["checklist"]` tells Claude the block format + daily file location.

## Files
- `bot.py` — import/setup, base point, on_ready loops, `!task` dispatch, block extraction in `do_task`,
  `!help` line. Backup `backups/bot.py.bak-20260917`.
- `CLAUDE.md` — env vars, omit keys, new section. Backup `backups/CLAUDE.md.bak-20260917`.
- `.gitignore` — `.claude/checklists/`.
- Vault: created `Mobile/Tasks/Recurring.md` (SPF AM, serum+moisturiser PM) and
  `Mobile/Tasks/2026-09-17.md` (+ haircut one-off).

## Verified
- Offline test (temp dir): build/carry-over/dedupe, toggle by line + hash fallback after lines move,
  add/rm, render labels/custom_ids, template regex match, block extraction.
- `import bot` OK. NOT live-tested: needs `discord-claude` restart (awaiting Gaurav's yes). Not committed.

## Revision 08:50 — daily notes + skills index (asked by Gaurav)
- Daily tasks moved from `Mobile/Tasks/` to the vault's own daily note:
  `DailyNotes/MMM DD, YYYY.md`, `## Tasks` section (appended to an existing journal note, or
  note created from `Templates/Default.md`). Recurring: `DailyNotes/Recurring Tasks.md`.
  `!task add` inserts at end of the section. Removed the two files I created at 08:22 in
  `Mobile/Tasks/` + the empty folder (Gaurav said not under Mobile). Today's note seeded.
- New shared skill `~/.claude/skills/discord-checklist/SKILL.md` (YAML frontmatter validated).
- New `skills.py`: scans `~/.claude/skills/*/SKILL.md` + `<cwd>/.claude/skills/` (native SKILL.md
  and loose category/*.md). Index (name — first sentence ≤90 — path) appended to every prompt via
  `build_points_block(cfg, cwd)`; `skills` base point replaces the `checklist` one. `!skills [project]`.
  Index sizes: 1.2k chars most channels, 2.5k animation, 5.9k zh-ai-support.
- Vault `CLAUDE.md` DailyNotes bullet mentions the Tasks section (backup `CLAUDE.md.bak-20260917`).
- Backups: `backups/checklist.py.bak-20260917`. Still not live-tested / not committed; restart pending yes.
