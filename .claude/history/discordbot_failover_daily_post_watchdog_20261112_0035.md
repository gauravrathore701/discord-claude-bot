# Failover: gate 07:00 task post + VM watchdog mode — 2026-11-12 00:35

- checklist.py: `_is_leader()`; `daily_loop()` skips posting on the failover standby, re-checks every 60 s.
  Tracking (messages.json) syncs, so the host that leads posts once. Needs a discord-claude restart.
- watchdog.sh: `WATCHDOG_HOST=vm` mode — exits unless role=leader (a restart on the standby would start a 2nd bot),
  skips the WiFi/NM/reboot ladder. Pi default unchanged. nmcli stderr silenced (VM has no NM).
  Backup ~/watchdog.sh.bak-20261112. VM unit sets the env var; timer every 5 min.
