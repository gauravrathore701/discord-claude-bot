# Pi→Monitor Media Playback + HDMI Control (Phase 1)

**Date:** 2026-07-09 18:50
**Project:** discord-claude-bot

## Goal
Let Gaurav play YouTube music/video on the Pi's HDMI monitor (Acer Nitro VG240Y) via
Discord commands, and auto-blank the monitor after 30 min idle while the Pi keeps
running. Monitor + Pi are powered 24/7; PC is on a second HDMI input (usually off
when the Pi is asked for the screen, so the monitor's Auto Source Select shows the Pi).

## Key discoveries (probed live before writing code)
These overturned the original plan, which had assumed a headless Pi:
- **The Pi is NOT headless.** It boots to `graphical.target` → lightdm auto-login →
  **labwc Wayland desktop** as user `gaurav` (uid 1000), seat0/tty1. The compositor
  owns DRM, so the originally-planned `mpv/vlc --vout=drm_vout` headless render would
  have produced a black screen.
- **`vcgencmd display_power` is dead on Pi 5** ("Command not registered"). Cannot be
  used for blanking.
- Correct tools (both already installed): **`wlr-randr`** for HDMI on/off, and VLC
  rendering into the existing labwc session.
- The bot runs as `gaurav` (uid 1000) too, so it can reach the compositor at
  `XDG_RUNTIME_DIR=/run/user/1000`, `WAYLAND_DISPLAY=wayland-0`.
- With the monitor unplugged, `wlr-randr` shows only `NOOP-1 "Headless output 2"` and
  the only audio sink is "Dummy Output" — both resolve to real `HDMI-A-1` + an HDMI
  sink once the monitor is connected. Code auto-detects them.

## What was built
- **New file `media.py`** — a `MediaPlayer` class (single shared instance; one physical
  monitor):
  - `play(query, video=False)` — `yt-dlp` resolves a `ytsearch1:` query (or raw URL)
    and pipes into `cvlc` via a shell pipeline (`yt-dlp -o - ... | cvlc ... fd://0`),
    launched with `start_new_session=True` so the whole pipeline is one process group.
    Audio mode: `--no-video` (no screen needed). Video mode: wakes HDMI first, then
    `--fullscreen`. Title is pre-resolved with `--print %(title)s` (WARNING/ERROR lines
    filtered out).
  - `stop()` — `os.killpg(SIGTERM→SIGKILL)` on the process group. Verified no orphans.
  - `display(on)` — `wlr-randr --output <HDMI-A-1> --on/--off`; auto-detects the first
    connected `HDMI*` connector; graceful error if monitor unplugged.
  - `_route_audio_to_hdmi()` — best-effort `wpctl set-default` to the HDMI sink.
  - Idle loop — every 60s; while playing it resets the clock (never blanks mid-video);
    otherwise blanks HDMI after `IDLE_TIMEOUT` (default 30 min, env `MEDIA_IDLE_TIMEOUT`).
- **`bot.py`** wiring:
  - `from media import MediaPlayer`; single module-level `MEDIA` instance.
  - Command handlers added in `on_message` **before** the per-channel concurrent-task
    guard, so media works even while a Claude task is running:
    - `!play <song|url>` — audio (no screen)
    - `!video` / `!playvideo <query|url>` — video (wakes monitor)
    - `!mstop` (also `!stopmusic`, `!mediastop`) — stop  *(note: `!stop` stays an alias of `!cancel`)*
    - `!wake` / `!screenon`, `!sleep` / `!screenoff` — HDMI on/off
    - `!np` / `!nowplaying` / `!mstatus` — status
  - `!help` text updated with a Media/monitor section.

## Other changes
- **Updated yt-dlp 2026.03.17 → 2026.07.04** (`sudo pip install -U --break-system-packages yt-dlp`).
  The old build was >90 days stale — the top cause of YouTube extraction breakage.

## Verification (monitor still unplugged)
- `python -c "import ast"` syntax check on both files: OK.
- `hdmi_output()` returns `None` when unplugged; `display()` fails gracefully.
- Title resolution: `"One Bottle Down" ... Yo Yo Honey Singh | T-SERIES` (clean, no warning line).
- Full audio pipeline: `play('one bottle down')` → streamed into dummy sink, `playing()`
  True, status correct, `stop()` killed cleanly, **no orphan yt-dlp/cvlc**.
- Service restarted → `Online as Claudy Rex#5707`, new `media` import loaded fine.

## Still to test WHEN THE MONITOR IS PLUGGED IN
1. In the Acer OSD, enable **Auto Source Select** (so it flips to the Pi's input).
2. `!wake` → confirm `wlr-randr` finds `HDMI-A-1` and the panel lights up.
3. `!play one bottle down` → sound from the monitor speakers (may need
   `_route_audio_to_hdmi` to pick the right sink; verify `wpctl status` shows an HDMI sink).
4. `!video ...` → fullscreen playback; check for stutter (VLC in labwc should be fine,
   unlike the drm_vout path we avoided).
5. Idle 30 min with nothing playing → HDMI blanks; `!wake` restores.

## Revert
- Remove the media command block + `from media import MediaPlayer` + `MEDIA = ...` from
  `bot.py`, delete `media.py`, restart `discord-claude`. (yt-dlp update is harmless, keep it.)

## Not done yet (Phase 2)
- Pause/resume (needs a VLC control interface, e.g. RC/HTTP — skipped in Phase 1).
- A play queue / auto-advance.
- Fliqlo-style flip clock / screensaver / image display (likely a Chromium-kiosk web
  clock coexisting with VLC; the bot arbitrates who owns the screen).
