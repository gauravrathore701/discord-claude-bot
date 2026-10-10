# discord-claude-bot — lock task lists after 3 days

Date: 2026-10-09 10:32

## Ask
Gaurav: after 3 days the older checkboxes in
Discord should be un-tickable. Pairs with the new
`daily-script/tasks/track_tasks.py`, which also
re-checks a 3-day window — once the tracker stops
looking, the buttons stop accepting edits.

## Changed — checklist.py only
Backup: `checklist.py.bak-20261009`

- `LOCK_AFTER_DAYS = 3` (new constant)
- `locked(key, today=None)` — daily keys only.
  Age in days >= 3 -> locked. Today, D-1, D-2
  stay open. Ad-hoc `c<hex>` lists never lock.
- `ToggleButton.__init__` takes `disabled`
- `render()` passes it, so every button on an old
  list renders greyed out, and the header gains
  `· 🔒 locked (over 3 days old)`
- `ToggleButton.callback` rejects a locked key
  with an ephemeral note, before touching the
  file. This covers a stale message whose view
  was built while the list was still open.
- `watch_loop()` now also re-renders when a list
  crosses the boundary, not only on file change,
  by remembering `locked` per message in
  `messages.json`. So a message posted 3 days ago
  visibly greys out on its own.

Verified boundary with the real function:
```
0,1,2 days old -> open
3,4   days old -> locked
adhoc          -> never
```

## Not changed
The markdown stays writable — Obsidian, `!task`
and Claude can still fix an old day by hand. Only
the Discord buttons are gated. Deliberate: the
lock is a speed bump against silent back-dating,
not a write-protect.

## Applied
Gaurav said go 11:06. Import verified with
venv python (LOCK_AFTER_DAYS=3, locked
d20261006 -> True), then restart queued via
`systemd-run --on-active=15` per the
restart-own-service skill.
