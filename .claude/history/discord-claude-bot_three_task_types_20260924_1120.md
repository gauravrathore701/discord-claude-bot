# Daily tasks — three types + section scoping

Date: 2026-09-24 11:20 IST
Files: `checklist.py`, `CLAUDE.md`,
`~/.claude/skills/discord-checklist/SKILL.md`

## Ask
Gaurav wanted three kinds of task, not one flat carried-over list:
1. daily — shows every day
2. one-time — gone once ticked
3. date-specific — appears on that date; if not ticked it
   carries to the next day, if ticked it never comes back

Plus: "remind me …" should also create a task.

## What was already there
Types 1 and 2 existed. `Recurring Tasks.md` is copied into
every note; unticked one-offs carry over and ticked ones drop.
The list looked like it repeated everything only because the
5 open items were never ticked before 07:00.

## Added — type 3
`DailyNotes/Scheduled Tasks.md`, one line per task:

    - [ ] 2026-10-01 | Pay credit card due

- `SCHED_RE` parses the `date | text` payload inside a checkbox
- `schedule_item(when, text)` appends a line
- `scheduled_items()` lists them
- `_take_due(today)` pulls every unticked line dated <= today
  and ticks it in place, so it is never injected twice
- `ensure_today()` appends the due items after recurring +
  carried, deduped by text hash
- `ensure_today()` also calls `_take_due()` on the early-return
  path, so a task scheduled for today *after* the 07:00 build
  still lands on today's list instead of tomorrow's

The 1-Oct/2-Oct rule then falls out of the existing carry-over:
unticked in the daily note -> carried; ticked -> dropped.
Nothing extra needed.

## Added — date parsing
`parse_when()` handles `1 oct`, `oct 1`, `1st oct`,
`2026-10-01`, `1/10`, `01-10-2026`, `today`, `tomorrow`, and
weekday names (`monday`, `next friday`). With no year it takes
the next occurrence, so "1 oct" typed in December means next
October. Returns None on anything unparseable, so
`!task add read on the train` stays a plain task.

`ON_RE` splits `<text> on|for <when>` off the end of an add.

## Added — commands
- `!task add <text> on <date>` — queue for that date
- `!task every <text>` — add to `Recurring Tasks.md` *and*
  today's list
- `!task sched` — list what is queued for later
- `!task add` with no text also prints the schedule

## Fixed — journal checkboxes leaking
`read_items()` scanned every checkbox in the file, so a
`- [ ]` written in the journal part of a daily note showed up
as a task button. Added `_section_bounds()` and a `section`
argument; `read_tasks(key)` reads only `## Tasks` for a daily
note, the whole file for an ad-hoc list. Callers updated:
`remove_item()`, `render()`, and the carry-over scan.

## Verified (scratch vault, bot venv)
- parse_when across 12 inputs incl. `garbage` and `31 feb`
  -> both None
- 1 Oct injects "Pay credit card due"; left unticked it shows
  on 2 and 3 Oct
- ticked on 3 Oct -> absent on 4 Oct
- 5 Oct pulls "Renew domain"; `Scheduled Tasks.md` lines are
  ticked and never re-injected
- same-day schedule after the section exists lands on today
- a `- [ ]` under `## Journal` is excluded from the task list
  while the whole-file read still sees it
- `py_compile` clean

## Not done
Service not restarted — waiting on Gaurav (bot restart rule).
`Scheduled Tasks.md` created empty in the real vault.

## Backups
- `checklist.py.bak-20260924`
- `~/.claude/skills/discord-checklist/SKILL.md.bak-20260924`

## Restart (appended 2026-09-24 15:15)
Restarted 14:14:28 on Gaurav's go. Bot back up same second,
all 8 channels, slash commands synced, `NRestarts=0`, no
errors in the hour since. Three-task-type code is live.

Method was wrong though: `sudo systemctl restart` ran
inline, systemd tore down the cgroup, and the Claude process
writing the confirmation died with it (exit 137). The
restart succeeded, the reply never arrived.

Correct method now captured in the new shared skill
`~/.claude/skills/restart-own-service/SKILL.md`:
`sudo systemd-run --on-active=15 --unit=... systemctl
restart discord-claude` — PID 1 owns the job, so it outlives
the cgroup and the reply goes out first. Verified the
transient timer fires and self-cleans.
