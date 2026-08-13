# DNS pin + watchdog self-heal — 2026-08-12 21:34

## Outage this fixes

Bot was offline ~2 days (Aug 10 ~21:30 → Aug 12 21:22, ended by a manual reboot).
`discord-claude` restart-looped every 15s the whole time; journal showed 500-670
`[Errno -3] Temporary failure in name resolution` per hour.

Root cause: `/etc/resolv.conf` was left with **zero** nameservers. Proof from the
same boot — syncthing resolving via `[::1]:53 connection refused`, which is the
libc/Go fallback used only when no nameserver is configured. NetworkManager is the
sole writer on this box (`ifupdown managed=false`, no dhcpcd/resolvconf); it blanks
the file when a connection drops and refills on reconnect, and that reconnect never
completed. A wifi drop did happen — the lease moved 192.168.1.2 → 192.168.1.14.

The existing watchdog did not help: it only restarts the bot, and the bot was not
the broken component.

## Changes

### 1. Pinned `/etc/resolv.conf` (host, not in repo)

```
sudo nmcli con mod Prestige_5G ipv4.dns-priority -42
printf '%s\n' 'nameserver 1.1.1.1' 'nameserver 8.8.8.8' \
  'nameserver 192.168.1.254' | sudo tee /etc/resolv.conf
sudo chattr +i /etc/resolv.conf
```

`chattr +i` means NetworkManager cannot truncate or rewrite the file, so a wifi
drop can no longer take host DNS with it. Router (192.168.1.254) is now last in
the list, behind Cloudflare and Google.

Verified: `lsattr` shows `----i---------e-------`, `getent hosts discord.com`
resolves.

To edit it later you must `sudo chattr -i /etc/resolv.conf` first.

### 2. `watchdog.sh` — check host DNS before blaming the bot

New block runs before the grace/heartbeat logic:

- `getent hosts discord.com` fails → log to syslog, `nmcli con up Prestige_5G`,
  re-test after 5s, log the outcome, `exit 0` (bot deliberately left alone).
- DNS fine → falls through to the unchanged heartbeat-stale logic.

Timer `discord-claude-watchdog.timer` runs the repo copy of the script directly
every 5m, as root, so no install step was needed.

## Verification

- `bash -n` clean; real run exited 0 and did not touch the unit (DNS healthy).
- Dead-DNS branch exercised with stub `getent`/`nmcli` on PATH: logged
  `DNS dead -> bouncing Prestige_5G` then `DNS still dead after bounce`, and left
  `discord-claude` running.

No bot restart was performed; `bot.py` and the service unit are unchanged.
