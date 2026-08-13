#!/bin/bash
# Restart discord-claude when its heartbeat goes stale.
#
# The bot can sit "active" in systemd with a dead gateway or dead DNS — process
# alive, Discord shows it offline, Restart=on-failure never fires. heartbeat_loop()
# in bot.py rewrites HB every HEARTBEAT_INTERVAL (120s) only after a real Discord
# API call succeeds, so a stale file means the bot is not actually reachable.

HB=/run/discord-claude/heartbeat
UNIT=discord-claude.service
WIFI=Prestige_5G
MAX_STALE=600     # 10m — 5 missed heartbeats
GRACE=300         # 5m — let a fresh start reach on_ready before judging it

now=$(date +%s)

# Host DNS first: on Aug 10-12 2026 the bot restart-looped for two days because
# NetworkManager blanked /etc/resolv.conf after a wifi drop. Restarting the bot
# cannot fix that, so heal the link instead and leave the unit alone this tick.
#
# Escalation ladder, one rung per 5m tick, counter in /run (clears on boot):
#   strike 1-2  bounce the wifi connection
#   strike 3    restart NetworkManager
#   strike 4+   reboot, at most once an hour, and never in the first 15m of a boot
STRIKES=/run/discord-claude/dns_strikes
REBOOT_STAMP=/var/lib/discord-claude-watchdog/last_reboot
REBOOT_COOLDOWN=3600
BOOT_GRACE=900

if ! getent hosts discord.com >/dev/null 2>&1; then
    n=$(( $(cat "$STRIKES" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$STRIKES"
    boot_s=$(cut -d' ' -f1 /proc/uptime | cut -d. -f1)

    if [ "$n" -le 2 ]; then
        logger -t discord-claude-watchdog "DNS dead (strike $n) -> bouncing $WIFI"
        nmcli con up "$WIFI" >/dev/null 2>&1
    elif [ "$n" -eq 3 ]; then
        logger -t discord-claude-watchdog "DNS dead (strike 3) -> restarting NetworkManager"
        systemctl restart NetworkManager
    else
        last=$(cat "$REBOOT_STAMP" 2>/dev/null || echo 0)
        if [ "$boot_s" -lt "$BOOT_GRACE" ]; then
            logger -t discord-claude-watchdog \
                "DNS dead (strike $n) -> reboot held, only ${boot_s}s since boot"
        elif [ $(( now - last )) -lt "$REBOOT_COOLDOWN" ]; then
            logger -t discord-claude-watchdog \
                "DNS dead (strike $n) -> reboot held, last one $(( (now - last) / 60 ))m ago"
        else
            mkdir -p "$(dirname "$REBOOT_STAMP")"
            echo "$now" > "$REBOOT_STAMP"
            logger -t discord-claude-watchdog "DNS dead (strike $n) -> rebooting"
            systemctl reboot
        fi
        exit 0
    fi

    sleep 5
    if getent hosts discord.com >/dev/null 2>&1; then
        logger -t discord-claude-watchdog "DNS back after strike $n"
        rm -f "$STRIKES"
    else
        logger -t discord-claude-watchdog "DNS still dead after strike $n"
    fi
    exit 0
fi

# Healthy resolution wipes the ladder so an old strike can't stack onto a new fault.
rm -f "$STRIKES"

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
