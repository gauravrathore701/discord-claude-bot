#!/bin/bash
# Restart discord-claude when its heartbeat goes stale.
#
# The bot can sit "active" in systemd with a dead gateway or dead DNS — process
# alive, Discord shows it offline, Restart=on-failure never fires. heartbeat_loop()
# in bot.py rewrites HB every HEARTBEAT_INTERVAL (120s) only after a real Discord
# API call succeeds, so a stale file means the bot is not actually reachable.

HB=/run/discord-claude/heartbeat
UNIT=discord-claude.service
MAX_STALE=600     # 10m — 5 missed heartbeats
GRACE=300         # 5m — let a fresh start reach on_ready before judging it

now=$(date +%s)

# Only judge a unit that has been up long enough to have written a heartbeat.
started=$(systemctl show "$UNIT" -p ActiveEnterTimestampMonotonic --value)
uptime_s=$(( ($(cut -d' ' -f1 /proc/uptime | cut -d. -f1) ) - started/1000000 ))
if [ "$uptime_s" -lt "$GRACE" ]; then
    exit 0
fi

if [ -f "$HB" ]; then
    age=$(( now - $(stat -c %Y "$HB") ))
    [ "$age" -lt "$MAX_STALE" ] && exit 0
    reason="heartbeat stale ${age}s"
else
    reason="heartbeat file missing"
fi

logger -t discord-claude-watchdog "$reason -> restarting $UNIT"
systemctl restart "$UNIT"
