# mediactl removed completely — 2026-07-31 23:15

Gaurav: "remove that mediactl functionality completely need to revamp that approach."

## Why it was dead weight

The whole stack assumed a **cage + Chromium kiosk on Wayland**, driven over CDP (port 9222)
plus `wlr-randr` for display power. Reality on this Pi since the 2026-07-25 change
(`54ab9ab Disable automatic display control, make monitor manual`):

- Session is **X11 + LXDE + Xorg** under lightdm — the desktop owns HDMI
- No cage, no kiosk, no CDP listener → every `status`/`play` call returned `kiosk/CDP not up`
- `cmd_display()` shelled out to `wlr-randr`, a wlroots-only tool → `couldn't switch HDMI-A-1`
  on every `wake`/`sleep`, regardless of cable state

Net: 834 lines of `mediactl.py` + 18 KB of `media.py` that could not succeed on the current
display stack. Removed rather than patched, per Gaurav — new approach to be designed fresh.

## Removed

| Path | Note |
|---|---|
| `mediactl.py` | 834 lines — CDP client, YouTube control, shows library, volume, display |
| `media.py` | `MediaPlayer` class used by `bot.py` |
| `static/flipclock.html` | kiosk idle screen |
| `static/wallpaper.mp4` | kiosk idle wallpaper |
| `/home/gaurav/.claude/skills/mediactl/` | the `/mediactl` skill (SKILL.md) |
| `__pycache__/media*.pyc` | stale bytecode |

Skill file backed up (outside git) to
`/home/gaurav/Projects/.mediactl-removed-20260731/mediactl_SKILL.md`.
Repo files are recoverable from git history — nothing is force-deleted.

## `bot.py` edits

- dropped `from media import MediaPlayer`
- dropped the module-level `MEDIA = MediaPlayer(...)` singleton
- dropped the `"media"` entry from `BASE_POINTS` (the MONITOR / YOUTUBE CONTROL bullet that
  was injected into every channel's prompt, every model)
- dropped the whole media command block from `on_message`: `!play`, `!video`, `!playvideo`,
  `!mstop` / `!stopmusic` / `!mediastop`, `!pause`, `!resume`, `!wake` / `!screenon`,
  `!sleep` / `!screenoff`, `!np` / `!nowplaying` / `!mstatus` — plus the now-unused
  `low = text.lower()` local
- dropped the Media/monitor section from `!help`
- rewrote the stale `on_ready` comment that referenced `MEDIA.startup()`

`CLAUDE.md`: `media` removed from the documented `omit` key list.

Verified: `grep -n "MEDIA\|mediactl\|mstop" bot.py` → no hits; `ast.parse(bot.py)` → OK.

## Not done

Service **not** restarted — per the bot restart rule, waiting on Gaurav's explicit yes.
Until then the running process still has the old code in memory.

## Context — same session

- HDMI was dead all of 30 Jul → fixed 31 Jul 09:10 by reseating the **micro-HDMI end** at
  the Pi (hotplug pin never made contact; cable tested fine on another PC because that only
  exercised the full-size end). `xrandr --output HDMI-1 --mode 1920x1080 --rate 60 --primary`
  + `xset s off -dpms` brought the desktop up at 1080p.
- Pi was then powered off / rebooted ~09:20–22:44 → bot offline ~13.5 h. Journal is volatile
  (`Storage=` not persistent) so the previous boot's logs are gone; cause unrecoverable.
  8 restarts at 22:46 were DNS failures while wlan0 came up, then it settled at 23:05:22.
- As of 23:09 both DRM connectors read `disconnected` again and the only PipeWire sink is
  `Dummy Output` — the display dropped a second time.
