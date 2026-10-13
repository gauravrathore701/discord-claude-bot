# Ponytail installed and wired into every channel

**Date:** 2026-10-12 11:30
**Asked for:** "install that ponytail skill into yourself and like
caveman plug it in every channel."

## What ponytail is
https://github.com/DietrichGebert/ponytail (MIT). Agent
minimalism ruleset — "lazy senior dev", smallest complete
change. Gaurav had already noted it in the vault on 6 Sep:
`Main/AI/AI Skills & Plugins.md`, entry 1.

Deliberately NOT installed via `/plugin marketplace add` — the
bot injects skills by reading a SKILL.md path, so the plugin
route would have left the file somewhere bot.py cannot see.
Copied the repo's `skills/` instead.

## Skills installed (shared, so every channel indexes them)
`~/.claude/skills/`: ponytail, ponytail-review, ponytail-audit,
ponytail-debt, ponytail-gain, ponytail-help.

## bot.py changes (backup: bot.py.bak-20261012)
Mirrored the caveman plumbing rather than refactoring it —
lower risk on a live service.

- `PONYTAIL_SKILL_FILE` / `PONYTAIL_LEVEL` env, default `full`.
- `PONYTAIL_LEVELS = ("lite","full","ultra")`, `_ponytail_cache`,
  `ponytail_prompt(level)` — frontmatter stripped, cached per
  level, `off` -> "".
- `ChannelState.ponytail`, `channel_paths()["ponytail"]`,
  `load_ponytail()` / `save_ponytail()` ->
  `.claude/sessions/<cid>/ponytail.json`.
- `set_ponytail()` + `/ponytail` application command +
  `^[!/]?ponytail(\s+\S+)?$` text handler. Same three entry
  points as caveman.
- `run_claude()` now joins the caveman and ponytail prompts with
  a blank line into ONE `--append-system-prompt` arg, instead of
  passing the flag twice.
- Webhook refusal regex extended to `ponytail`.
- Startup log prints the ponytail default + any channel override.
- `!help` lists `/ponytail`.

## Why one flag, not two
`--append-system-prompt` passed twice is not documented as
additive, so the two prompts are concatenated. The ponytail
preamble states that caveman governs PROSE and ponytail governs
CODE, so neither reads as overriding the other.

## Verified
- `ast.parse` clean.
- Imported bot.py under `venv/bin/python`: `PONYTAIL_LEVEL=full`,
  choices `(lite, full, ultra, off, default)`, prompt lengths
  full 3357 / ultra 3359 / off 0 chars.
- Skills already visible in this session's own skill index, so
  the SKILL.md frontmatter parses.

## NOT done
Service not restarted — per the bot-restart rule, waiting on
Gaurav's explicit yes. Until then the running process has none
of this: no `/ponytail` command, no injection.

Gaurav said he will give per-channel levels after the restart.
Set them with `/ponytail <level>` in each channel, or change the
global default with `PONYTAIL_LEVEL` in `.env` (no entry there
yet — it is falling back to the code default).

## Per-channel levels set (2026-10-12 12:10)
Gaurav: "for code, zh-ai-support and rex-chat (obsidian one)
mark this three as ponytail ultra."

"code" resolved to the `__DEFAULT__` / `projects` entry — its
Discord channel is literally named **rex-code**
(id 1508034842304970772, confirmed via the channels API).
"rex-chat" = the obsidian channel, per the standing note.

Wrote `{"ponytail": "ultra"}` to
`.claude/sessions/<cid>/ponytail.json` for:
- 1508034842304970772  projects / rex-code
- 1528641869637095444  zh-ai-support
- 1508034882645786644  obsidian / rex-chat

Everything else stays on the `full` code default. Resolved
matrix verified by importing bot.py and calling
`load_ponytail()` per channel:

    projects       ponytail=ultra  caveman=ultra
    obsidian       ponytail=ultra  caveman=lite
    zh-ai-support  ponytail=ultra  caveman=ultra
    blog           ponytail=full   caveman=off
    pi-ops         ponytail=full   caveman=ultra
    finance        ponytail=full   caveman=ultra
    animation      ponytail=full   caveman=ultra
    daily-tasks    ponytail=full   caveman=ultra

Note: ponytail is a coding skill, so on finance / daily-tasks /
animation `full` is mostly inert. Left as-is rather than
switching them off on my own initiative.

## Post-restart verification (2026-10-12 12:14)
Service healthy:

    is-active            active
    ActiveEnterTimestamp 12:10:32 IST
    NRestarts            0
    MainPID              272077

Startup log confirms both dials and the sync:

    caveman default: ultra (3605 chars)
    ponytail default: full (3357 chars)
    projects:      ponytail override -> ultra
    obsidian:      ponytail override -> ultra
    zh-ai-support: ponytail override -> ultra
    slash commands synced to guild
      1150691625312456734: ['ponytail','caveman']

### Caveat found: --resume ignores a new --append-system-prompt
The live `claude` process (pid 272121) DOES carry the ponytail
text — 27 matches in /proc/<pid>/cmdline, including
"The /ponytail skill is ACTIVE ... `/ponytail ultra`" — but the
model's actual system prompt this turn contained the caveman
block and NOT the ponytail block.

Difference: the invocation also has `--resume`. A resumed
session reuses the system prompt captured when the session was
created, so a newly added `--append-system-prompt` does not
apply to it. Caveman is present only because it predates the
session.

Consequence: ponytail takes effect per channel on the next
FRESH session — `!newsession`, or the 06:30 daily rollover.
Nothing to fix in the code; worth knowing for any future
system-prompt change, which will have the same lag.
