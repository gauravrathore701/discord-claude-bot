# mediactl: Bluetooth follows the monitor

**Date:** 2026-07-14 00:15
**File edited:** `/home/gaurav/.claude/skills/mediactl/SKILL.md`

## What Gaurav asked
Whenever he asks to turn the monitor **on**, turn Bluetooth **on** with it by default;
whenever he asks to turn the monitor **off**, turn Bluetooth **off** with it.

## What was done
1. Updated the intent→command mapping for wake/sleep to note the coupled Bluetooth action.
2. Added a new **"Bluetooth follows the monitor (default)"** section:
   - Monitor ON → `mediactl.py wake` **and** `bluetoothctl power on`
   - Monitor OFF → `mediactl.py sleep` **and** `bluetoothctl power off`
   - Default behavior; skip only if Gaurav explicitly says to leave BT alone (e.g. pairing).
   - Report both results briefly.

## Verification
- `bluetoothctl` present at `/usr/bin/bluetoothctl`, runs without sudo.
- `bluetoothctl power on/off` is the control used; adapter currently Powered: yes.

## Context
Follows the earlier session where the BT service was enabled at boot and the Toad II
mouse was being paired. Coupling BT to the screen keeps mouse/keyboard available whenever
the desktop is on.
