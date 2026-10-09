# discord-claude restart — apply channel config

Date: 2026-10-08 08:45

## Why
Four channel config files were edited on disk at 00:20 but
bot.py only reads them in `on_ready()`, so the running
process kept the old in-memory values. Gaurav approved the
restart.

## Changes applied (written earlier, no new edits now)
- `1508034882645786644/model.json` -> `{"model":"sonnet"}` (rex-chat)
- `1508034882645786644/caveman.json` -> `{"caveman":"lite"}`
- `1537133272319008798/caveman.json` -> `{"caveman":"ultra"}` (claudy-logs)
- `1545758605465100449/caveman.json` -> `{"caveman":"ultra"}` (claudy-cmds)

Backups from the original change: `*.bak-20261008`.
No code touched. No files deleted.

## How restarted
Per `restart-own-service` skill — detached transient timer so
this reply survives the cgroup teardown:

    sudo systemd-run --on-active=15 \
      --unit=discord-claude-restart \
      systemctl restart discord-claude

JSON validity of all four files verified before scheduling.

## Discussion dropped
Gaurav asked about moving config to Mongo/Redis to avoid
restarts. Conclusion: restart need is in-memory caching, not
disk. Options were mtime invalidation, inotify (`watchfiles`),
or a SIGHUP reload handler. He chose to drop it and just
restart. Nothing implemented.

## Verify next session
    systemctl is-active discord-claude
    systemctl show discord-claude \
      -p ActiveEnterTimestamp,NRestarts
