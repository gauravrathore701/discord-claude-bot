# mediactl — shows-app library playback (`shows` command)

**Date:** 2026-07-16 23:50
**File:** `discord-claude-bot/mediactl.py` (+ `~/.claude/skills/mediactl/SKILL.md`)

## What was added

A new `shows` command to `mediactl.py` that opens Gaurav's own **shows-app**
(Cursed Shrine library, files on `/mnt/hdd`) on the Pi monitor and plays specific
titles — separate from the existing YouTube `play`/`video` commands.

```
mediactl.py shows play <show [ep / SxxExx / season N episode M]>   # find & play on monitor
mediactl.py shows search <query>                                   # list matching shows (no playback)
mediactl.py shows open [show]                                      # library home, or a show's page
mediactl.py shows list                                             # all shows + episode counts
```
Bare `shows <query>` == `shows play <query>`. Aliases: `show`, `library`, `lib`.

## How it works

- **Resolution is local, off the filesystem** — the shows-app has no search endpoint,
  and `/mnt/hdd` is on the same Pi, so mediactl reads it directly:
  - `_list_shows()` — top-level dirs (skips hidden + `lost+found`).
  - `_list_episodes(show)` — flat (direct video files) or seasonal (video files in
    subdirs), each entry carrying URL path `segs`.
  - `_resolve_show(query)` — scores shows (exact > prefix > substring > token overlap),
    returns best match + leftover text as an episode/season hint.
  - `_match_episode(eps, hint)` — understands compact `s05e12` **and** worded
    "season 5 episode 12", bare episode numbers, `E03`/`ep3`/`episode 3`/`x03` markers,
    parses each file's own `SxxExx`. Falls back to first episode. Movies = the single file.
- **URL**: builds `/watch/<show>/<segs…>` (URL-encoded) — the same route the app's own
  UI links to; the watch page auto-detects HEVC → HLS vs. direct codec.
- **Base URL**: prefers `http://localhost:4178` (on-device, no tunnel latency); falls
  back to `https://shows.cursedshrine.com` if localhost is down. Override: `SHOWS_BASE_URL`.
- **Auth**: the app's `AuthGate` only checks a JWT in `localStorage['shows_auth']`
  client-side — the stream API and page routes do **no** server-side auth. So
  `_shows_goto()` lands on the origin, seeds a long-lived kiosk token
  (`{"sub":"kiosk","exp":4102444800}`, far-future exp so AuthGate keeps it), then
  deep-links to the watch URL. (The local `user_auth` Mongo is empty post-Atlas-repoint,
  so real login wasn't dependable anyway.)
- **Playback**: wakes HDMI, navigates, polls for the `<video>` playing, then requests
  fullscreen. HEVC/x265 gets a longer confirm window (50s vs 30s) for HLS transcode
  cold-start (~15s on the Pi).

## Verified (real, against live kiosk)

- `shows list` / `shows search one piece` → correct JSON.
- Resolver spot-checks (all correct): `One Piece 1162`, `Adventure Time s3e5`,
  `Adventure Time season 5 episode 12`, `raakh episode 3`, `GOTS3 e4`, `Oppenheimer`,
  `blade runner`.
- **`shows play One Piece`** → deep-linked, AuthGate bypassed, `playing: true` on the
  monitor (status confirmed video element playing on the shows page).
- HEVC path (`Adventure Time s1e1`, x265→HLS) → correct page/URL loaded; `playing`
  reported false within the window (transcode warmup) — expected, note communicates it.
- Returned screen to idle flip-clock afterward (`shows`/`stop` unaffected).

## Notes / limitations

- No fuzzy typo matching (e.g. `oppenhimer` → no match). Deliberate; keep queries close.
- Kiosk auth is a seeded token, not a real user session — fine because the app does no
  server-side auth. If Gaurav ever adds server-side auth to shows-app, this needs a real
  JWT from `/api/auth/login` instead.
- SKILL.md updated with `shows` table rows, a library subsection, and intent mappings.
