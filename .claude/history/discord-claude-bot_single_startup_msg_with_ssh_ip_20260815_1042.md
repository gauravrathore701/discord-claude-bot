# Single startup message with SSH IP — 2026-08-15

## Ask
Stop broadcasting "Claude Code bot is online (<channel>). Send a task or type
`!help`." to all three configured channels on every restart. Post one message
instead, only in channel `1537133272319008798`, saying Claudy Rex is online and
carrying the Pi's current LAN IP so Gaurav can ssh in when the Claude account
logs out (otherwise the Pi needs a monitor + keyboard to recover).

## Changes — `bot.py`

1. **`STARTUP_CHANNEL_ID`** (new config, near `HEARTBEAT_FILE`)
   `int(os.environ.get("STARTUP_CHANNEL_ID", "1537133272319008798"))`.
   Overridable from `.env`; no `channels.json` entry needed because the channel
   only receives the announcement, it does not run tasks.

2. **`lan_ip()`** (new async helper, above the bot events section)
   Runs `ip -4 route get 1.1.1.1` as a subprocess (10s timeout) and regexes the
   `src <addr>` field. `hostname -I` was rejected — it also lists `172.17.0.1` /
   `172.18.0.1` docker bridges and the IPv6 address, none reachable for ssh from
   the phone. Never raises: on failure it logs and returns `""`.

3. **`on_ready` broadcast replaced**
   Old: `for cid, cfg in CHANNELS.items(): ... await ch.send(...)` — three pings
   for one restart.
   New: single `client.get_channel(STARTUP_CHANNEL_ID)`; if not visible, logs
   `startup channel <id> not visible — no online message` and sends nothing.
   Message body:

   ```
   **Claudy Rex online.**
   ```
   ```
   ssh gaurav@192.168.1.9
   ```

   If `lan_ip()` returns empty, the ssh block is replaced with
   `IP lookup failed — try \`raspberrypi.local\`.`

## Verified (without restart)
`venv/bin/python` import of `bot` on the real `.env` succeeds;
`STARTUP_CHANNEL_ID` resolves to `1537133272319008798`;
`await lan_ip()` returns `192.168.1.9`, matching `ip -4 route get 1.1.1.1`.

## Docs
`CLAUDE.md` — `STARTUP_CHANNEL_ID` documented in Environment Variables.

## Not done
Service not restarted (BOT RESTART RULE — waiting on Gaurav's yes). Until the
restart, the old three-channel broadcast is still what runs.

## Notes / risks
- The bot must have Send Messages permission in `1537133272319008798` and share
  that guild, else the message is silently skipped (logged to the journal).
- The IP is captured at `on_ready` only. A DHCP re-lease after startup (this has
  happened: `.2` -> `.14` -> `.9`) makes the posted IP stale until next restart.
  `raspberrypi.local` over mDNS is the stable fallback; a static
  `ipv4.method manual` lease on Prestige_5G would fix it permanently.
