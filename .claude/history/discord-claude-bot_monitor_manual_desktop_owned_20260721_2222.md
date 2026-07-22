# Monitor → manual / desktop-owned (kill scripted display control)

**Date:** 2026-07-21 22:22

## Problem
Pi has 1 GPU / 1 DRM connector (`card1` / HDMI-A-2). Two things fought for it:
- LXDE desktop via `lightdm`
- discord-claude cage/Chromium **flip-clock kiosk** (`MEDIA.startup()` on `on_ready`)

`discord-claude.service` is `After/Wants=network-online.target` → only starts when wifi is up. So:
- Boot **with wifi** → bot starts → cage grabs DRM → races `lightdm` → **black screen / cursor-only**.
- Boot **without wifi** → bot never starts → desktop owns display cleanly → GUI works.

Also DPMS + `xscreensaver` were blanking the monitor on idle.

## Decision (Gaurav)
Monitor = **manual, desktop-owned, always ON at every restart**, only off when explicitly requested. No script auto-controls the physical display.

## Changes
1. **lightdm** — `systemctl enable --now lightdm` → LXDE autologin on HDMI every boot.
2. **Monitor never blanks (persistent):**
   - `~/.local/bin/monitor-always-on.sh` → `xset s off / s noblank / -dpms` + `xscreensaver-command -exit`.
   - `~/.config/autostart/monitor-always-on.desktop` → runs it at every login.
   - `~/.xscreensaver` → `mode:off`, `dpmsEnabled:False`.
   - Applied live: `timeout 0`, `DPMS is Disabled`.
3. **Bot boot auto-kiosk removed** — `bot.py` `on_ready()`: `asyncio.create_task(MEDIA.startup())` commented out with note. Bot no longer grabs display at boot.
4. **Idle-blank disabled** (earlier) — `media.py` `IDLE_BLANK` env, default `0`; blank block guarded.
5. Killed the stray fullscreen chromium (parented to `lxpanel-pi`) that had covered the desktop.

## Left manual-only
`!play` / `!youtube` / display on/off / `mediactl.py` still exist but are user-triggered and inert while the desktop owns DRM. Not removed — YouTube-on-TV path preserved for if Gaurav switches back later.

## Pending
`sudo systemctl restart discord-claude` NOT yet run (awaiting confirm) → `bot.py` change loads on next restart/reboot. Desktop already wins now since the running bot's cage attempt already failed.

## Verify status
- `xset q` → `timeout: 0`, `DPMS is Disabled` ✓
- `bot.py` `python -m ast` parse OK ✓
- Desktop procs alive: `openbox`, `lxpanel-pi`, `pcmanfm --desktop` ✓
