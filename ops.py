"""
Native ops commands for the #pi-ops Discord channel.

Everything here runs locally in the bot process — no Claude call, no tokens
spent. bot.py dispatches to `handle(text)` before it ever reaches the model.
"""

import json
import os
import re
import socket
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

CREDENTIALS = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
REMINDERS_FILE = "/home/gaurav/Projects/daily-script/reminder/reminders.txt"

# !reboot is two-step. This holds the deadline for the confirm step.
_reboot_armed_until: float = 0.0
REBOOT_CONFIRM_WINDOW = 60  # seconds


def _ist(iso: str | None) -> str:
    if not iso:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IST)
    except ValueError:
        return iso
    delta = dt - datetime.now(IST)
    mins = int(delta.total_seconds() // 60)
    if mins < 0:
        rel = "passed"
    elif mins < 60:
        rel = f"in {mins}m"
    elif mins < 1440:
        rel = f"in {mins // 60}h {mins % 60}m"
    else:
        rel = f"in {mins // 1440}d {(mins % 1440) // 60}h"
    return f"{dt:%a %d %b %H:%M} IST ({rel})"


def _bar(pct: float) -> str:
    filled = int(round(pct / 10))
    return "█" * filled + "░" * (10 - filled)


def usage() -> str:
    """Current Claude session + weekly usage, straight from the OAuth endpoint."""
    try:
        with open(CREDENTIALS) as f:
            oauth = json.load(f)["claudeAiOauth"]
    except (OSError, KeyError, json.JSONDecodeError) as e:
        return f"Cannot read Claude credentials: {type(e).__name__}"

    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {oauth['accessToken']}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-cli/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001 - report any failure to Discord
        return f"Usage lookup failed: {type(e).__name__} {e}"

    lines = ["**Claude usage**", ""]
    for key, label in (("five_hour", "Session (5h)"), ("seven_day", "Weekly (7d)")):
        block = data.get(key) or {}
        pct = block.get("utilization")
        if pct is None:
            continue
        lines.append(f"**{label}** — {pct:.0f}%")
        lines.append(f"`{_bar(pct)}`")
        lines.append(f"resets {_ist(block.get('resets_at'))}")
        lines.append("")

    opus = data.get("seven_day_opus") or {}
    if opus.get("utilization") is not None:
        lines.append(f"**Opus (7d)** — {opus['utilization']:.0f}%")
        lines.append(f"resets {_ist(opus.get('resets_at'))}")
        lines.append("")

    worst = max(
        (l for l in data.get("limits", []) if l.get("is_active")),
        key=lambda l: l.get("percent", 0),
        default=None,
    )
    if worst and worst.get("severity") in ("warning", "critical"):
        lines.append(f"⚠️ **{worst['severity']}** on `{worst.get('kind')}` "
                     f"at {worst.get('percent')}%")

    plan = oauth.get("subscriptionType") or "unknown"
    lines.append(f"plan: `{plan}`")
    return "\n".join(lines).strip()


def ip() -> str:
    """LAN address, public address, and which interface is carrying the default route."""
    lan = "unknown"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
        s.close()
    except OSError:
        pass

    iface = "unknown"
    try:
        out = subprocess.run(["ip", "route", "get", "8.8.8.8"],
                             capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"\bdev\s+(\S+)", out)
        if m:
            iface = m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass

    public = "unknown"
    try:
        req = urllib.request.Request("https://api.ipify.org",
                                     headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=10) as r:
            public = r.read().decode().strip()
    except Exception:  # noqa: BLE001
        public = "lookup failed"

    host = socket.gethostname()
    return (f"**Pi network**\n"
            f"```\n"
            f"host    {host}\n"
            f"lan     {lan}\n"
            f"iface   {iface}\n"
            f"public  {public}\n"
            f"```")


def reboot(arg: str) -> str:
    """Two-step. `!reboot` arms it, `!reboot confirm` within 60s actually reboots."""
    global _reboot_armed_until
    import time

    now = time.time()
    if arg.strip().lower() != "confirm":
        _reboot_armed_until = now + REBOOT_CONFIRM_WINDOW
        return ("⚠️ **This reboots the whole Pi.** Every service goes down: "
                "the tunnel, all sites, this bot.\n\n"
                f"Send `!reboot confirm` within {REBOOT_CONFIRM_WINDOW}s to proceed.")

    if now > _reboot_armed_until:
        return "Confirmation window expired. Send `!reboot` again first."

    _reboot_armed_until = 0.0
    # Detached: a direct `systemctl reboot` would kill this process mid-reply,
    # because the bot lives inside its own unit's cgroup.
    try:
        subprocess.run(
            ["sudo", "systemd-run", "--collect", "--unit=pi-reboot-once",
             "--on-active=10", "systemctl", "reboot"],
            capture_output=True, text=True, timeout=15, check=True)
    except subprocess.CalledProcessError as e:
        return f"Reboot failed to schedule: {e.stderr.strip()[:300]}"
    except (OSError, subprocess.SubprocessError) as e:
        return f"Reboot failed to schedule: {type(e).__name__}"

    return ("🔄 **Rebooting in 10 seconds.** Back in roughly 40-60s.\n"
            "Send `!ip` once it is up to confirm the address did not change.")


_WHEN_DAILY = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_WHEN_ONCE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+([01]?\d|2[0-3]):([0-5]\d)$")


def _parse_when(raw: str) -> tuple[str | None, str]:
    """Return (line_prefix, human) or (None, reason)."""
    s = raw.strip().lower()
    now = datetime.now(IST)

    if _WHEN_DAILY.match(s):
        h, m = s.split(":")
        return f"{int(h):02d}:{m}", f"every day at {int(h):02d}:{m}"

    if _WHEN_ONCE.match(s):
        d, h, m = _WHEN_ONCE.match(s).groups()
        return f"{d} {int(h):02d}:{m}", f"once on {d} at {int(h):02d}:{m}"

    m = re.match(r"^\+(\d+)\s*([hm])$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        when = now + (timedelta(hours=n) if unit == "h" else timedelta(minutes=n))
        return f"{when:%Y-%m-%d %H:%M}", f"once at {when:%Y-%m-%d %H:%M}"

    m = re.match(r"^(today|tomorrow)\s+([01]?\d|2[0-3]):([0-5]\d)$", s)
    if m:
        day = now if m.group(1) == "today" else now + timedelta(days=1)
        stamp = f"{day:%Y-%m-%d} {int(m.group(2)):02d}:{m.group(3)}"
        return stamp, f"once on {stamp}"

    return None, ("Could not read the time. Use `HH:MM` (daily), "
                  "`YYYY-MM-DD HH:MM`, `today HH:MM`, `tomorrow HH:MM`, "
                  "`+2h` or `+30m`.\n"
                  "For anything fuzzier, drop the `!` and just ask — "
                  "that goes to Claude.")


def remind(arg: str) -> str:
    """`!remind <when> | <message>` -> one line appended to reminders.txt."""
    if "|" not in arg:
        return ("Usage: `!remind <when> | <message>`\n"
                "e.g. `!remind tomorrow 09:00 | pay the electricity bill`\n"
                "`when` accepts `HH:MM` (daily), `YYYY-MM-DD HH:MM`, "
                "`today/tomorrow HH:MM`, `+2h`, `+30m`.")

    when_raw, _, msg = arg.partition("|")
    msg = msg.strip()
    if not msg:
        return "The message is empty. Put it after the `|`."
    if "," in msg:
        msg = msg.replace(",", ";")

    prefix, human = _parse_when(when_raw)
    if prefix is None:
        return human

    line = f"{prefix},{msg}"
    try:
        with open(REMINDERS_FILE, "a") as f:
            f.write(line + "\n")
    except OSError as e:
        return f"Could not write the reminder: {type(e).__name__}"

    return (f"✅ Reminder saved — **{human}**.\n"
            f"```\n{line[:300]}\n```\n"
            "The notifier picks it up on its next run.")


HELP = (
    "**Pi ops commands** (no Claude call, no tokens)\n"
    "`!usage` — Claude session + weekly usage, with reset times\n"
    "`!ip` — LAN address, public address, interface\n"
    "`!reboot` — reboot the Pi (asks to confirm)\n"
    "`!remind <when> | <message>` — add a reminder\n"
    "`!ops` — this list\n\n"
    "Anything without a leading `!` goes to Claude as normal."
)


def handle(text: str) -> str | None:
    """Return a reply string if this is an ops command, else None."""
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "!usage":
        return usage()
    if cmd == "!ip":
        return ip()
    if cmd == "!reboot":
        return reboot(arg)
    if cmd == "!remind":
        return remind(arg)
    if cmd in ("!ops", "!opshelp"):
        return HELP
    return None
