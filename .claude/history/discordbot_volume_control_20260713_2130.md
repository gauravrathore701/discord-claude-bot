# Volume control added to mediactl.py + skill

**Date:** 2026-07-13

## Changes

### mediactl.py
- `_wpctl_env()` — builds subprocess env with `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` for PipeWire access
- `_wpctl_get_volume()` — reads `wpctl get-volume @DEFAULT_AUDIO_SINK@`, returns `(float, bool)` tuple
- `cmd_volume(arg)` — handles: absolute (70/70%), relative (+10/-10), up/down/louder/quieter, mute/unmute/toggle
- `cmd_status()` — now includes `volume` and `muted` fields in JSON output
- `main()` — wired `volume`, `vol`, `v`, `mute`, `unmute` commands

### ~/.claude/skills/mediactl/SKILL.md
- Updated description to include volume/mute triggers
- Added Volume command to command table
- Added volume args table
- Added volume/mute examples to intent→command mapping

## Audio backend
PipeWire 1.4.2 with WirePlumber. Default sink: Built-in Audio Digital Stereo (HDMI), node 70.
`wpctl set-volume @DEFAULT_AUDIO_SINK@` works correctly from bot subprocess context.
