# Pi System Analysis — "Q on LShift" + /login failures (2026-07-18 02:15)

## Symptoms reported
1. Discord bot replied `[error] Not logged in · Please run /login` to all queries (~00:15).
2. At a terminal on the Pi, pressing LShift "typed Q"; screenshot showed floods of `^[OQ` / `^[[1;5Q` around Claude Code's trust prompt.

## Root causes found (no code changed — diagnosis only)

### 1. /login errors — Claude CLI OAuth token had expired
The bot shells out to the `claude` CLI; its OAuth token expired, so every request returned "Not logged in". Username/password can't fix this — it's Anthropic OAuth only. **Resolved**: Gaurav logged in interactively at the Pi (~02:03, `~/.claude/.credentials.json` refreshed); bot works again.

### 2. "Q on LShift" — faulty/ghosting Toad II Bluetooth keyboard, NOT the OS
- Terminals encode **F2 as `ESC O Q`** and Ctrl+F2 as `ESC [1;5Q`. Bash swallows the `ESC O` prefix and self-inserts the trailing **Q** — so phantom F2 presses look like "typing Q".
- The Toad II BT keyboard (connected 01:57, hid-generic 0005:000E:3412) was spamming phantom F2 keypresses (stuck key / low battery / BT interference — classic cheap-BT-keyboard ghosting). It disconnected on its own at 02:07.
- Kernel, XKB config (pc105/us), and libinput are all normal. Escape sequences prove the keyboard genuinely sent F2 at HID level.

### 3. Boot config was changed (bash history) — side effects
```
sudo raspi-config nonint do_boot_behaviour B4   # desktop autologin
sudo raspi-config nonint do_wayland W1          # Wayland → X11
sudo systemctl set-default graphical.target
sudo reboot                                     # ← the 01:50 reboot
```
Consequences:
- Pi now boots to **X11 + LightDM desktop** (was console + cage kiosk owning DRM).
- **Kiosk/mediactl broken**: cage can't grab DRM ("desktop may own DRM"); `mediactl status` → `kiosk/CDP not up`. Flip-clock dead, monitor playback dead until reverted (or mediactl adapted to X11).
- **rpi-connect-wayvnc crash-loops every 5s** (needs Wayland; none exists under X11). Log spam, harmless.

### 4. External HDD (`/mnt/hdd`) missing after reboot
- `lsblk`/`lsusb`: **no USB devices at all** — the drive never enumerated this boot. Mount dir empty (fstab `nofail` let boot continue). No over-current/undervoltage logged; throttled=0x0.
- Physical issue: cable/power/spin-up. Needs a **physical replug**. Until then `shows` commands have no library (shows-app itself returns 200 but empty).

## System health otherwise
17-min uptime, load 0.02, 58.2°C, no throttling, 11 GiB free RAM, 60 GB free on SD. No other errors in journal.

## Recommended next steps (pending Gaurav's confirmation — needs reboot)
1. Replug/power-cycle the external HDD → verify `lsblk` shows sda → `sudo mount -a`.
2. Revert boot: `sudo raspi-config nonint do_boot_behaviour B2` (console autologin) + `do_wayland W3` (labwc) → reboot → kiosk/mediactl restored.
3. Replace batteries in / re-pair the Toad II keyboard before trusting it again.

## Correction (02:30, after Gaurav's feedback)
- **Keyboard theory retracted.** Gaurav was typing from his Windows laptop via **Raspberry Pi Connect remote shell** (browser terminal), not the Toad II (only its mouse was on). The F2 escape flood (`ESC O Q`, `ESC [1;5Q`) came from the browser terminal misencoding modifier/held keys while Claude Code had the terminal in raw/enhanced-key mode — same class as the documented Shift+Enter encoding bugs (Ghostty `[27;2;13~`, iTerm `OM`). His laptop keyboard and the Pi input stack are fine. Avoid running `claude` inside Pi Connect remote shell; use plain SSH.
- **HDD**: manually disconnected by Gaurav on purpose — not a failure. He'll announce reconnection.
- **/login**: two separate confusions — the real claude OAuth expiry (he fixed via local login) and the `[error] Not logged in` text he pasted, which he'd mistaken for a shows-project error.
- **Future re-login procedure** (documented for Gaurav): plain SSH → `claude` → `/login` → open OAuth URL on laptop browser → paste code. No GUI boot switch, no reboot, no raspi-config ever needed.
