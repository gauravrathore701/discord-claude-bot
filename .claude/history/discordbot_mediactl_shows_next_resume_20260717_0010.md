# mediactl — shows next / prev / resume (continue watching)

**Date:** 2026-07-17 00:10
**File:** `discord-claude-bot/mediactl.py` (+ `~/.claude/skills/mediactl/SKILL.md`)

## What was added

Relative episode playback for the shows library, so "play the next episode of X" works:

```
mediactl.py shows next <show>       # episode after the last one played on the monitor
mediactl.py shows prev <show>       # previous episode
mediactl.py shows resume <show>     # replay the last-watched episode (continue)
mediactl.py shows play <show> next  # same as `shows next` (relative word inside query)
```
Aliases: `previous`, `continue`. A relative word anywhere in a `play` query is honored too.

## How it works

- **Last-played memory** — mediactl now writes a per-show pointer to
  `~/.cache/mediactl/shows_state.json` (`SHOWS_STATE_FILE`) on **every** shows play:
  `{ "<show>": {file, season, ts} }`. Reliable + timestamped.
- **Resolution** (`_current_file`): mediactl's own state first; falls back to the app's
  `localStorage['lastWatched']` (keyed `<show>` or `<show>/<season>` → filename), read over
  CDP while on the shows origin.
- **Next/prev** = index ±1 in the flat, season-ordered episode list (`_list_episodes`), so it
  rolls across season boundaries and naturally skips gaps in episode numbering. Clamped at both
  ends with an explanatory `note` ("already at the last episode…"). No history → starts at the
  first episode with a note.
- Refactored the old `_shows_goto` into `_shows_land` (wake + land on origin + seed kiosk token)
  + `_shows_goto` (land then deep-link). Relative playback uses `_shows_land` so it can read
  `lastWatched` before choosing the target, then navigates to `/watch/…`.
- Play logic extracted from `cmd_shows` into `_shows_play(query, rel=None)`.

## Verified (real, against live kiosk / monitor)

- Offline unit check: recorded S03E05 → next=S03E06, prev=S03E04 (cross-checked indices).
- Relative-keyword parse: `next`→+1, `previous`/`prev`→-1, `resume`/`continue`→0.
- **Live monitor:** `shows play One Piece 1161` → 1161 playing → `shows next One Piece` → **1162
  playing** → `shows prev One Piece` → **1161 playing** → `shows resume One Piece` → **1161
  playing**. All `playing: true`. Returned to flip-clock after.

## Caveats

- Tracks **monitor** playback only (Pi kiosk state + kiosk-browser localStorage). Episodes
  watched on his phone don't advance the pointer. True cross-device resume would need the app
  to persist progress server-side.
- State file is per-show "last played", not a resume *timestamp* — `resume` replays the episode
  from the start, it doesn't seek to where he stopped.
