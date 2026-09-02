# discord-claude-bot — gateway-aware heartbeat

Date: 2026-09-01 13:50 IST

## Incident

Discord gateway cluster `us-east-1a` returned HTTP 503 on the
websocket upgrade from 02:48 (intermittent) and continuously from
06:19 until the Pi rebooted at 13:21.

```
aiohttp.client_exceptions.WSServerHandshakeError: 503,
message='Invalid response status',
url='wss://gateway-us-east-1a.discord.gg/?v=10&encoding=json&compress=zlib-stream'
```

discord.py exponential backoff climbed to 241s -> 288s -> 920s ->
522s, so the bot slept through most of the outage window.

The bot showed **available** in Discord the whole time: presence is
owned by the gateway session, and a degraded cluster never processed
a clean session close, so the last-known presence stuck.

Ruled out: Pi was up the entire 30h (journal continuous, ~3500
lines/hr), zero NetworkManager wifi events since Aug 31,
`throttled=0x0`, no OOM kills. Not a local fault.

## Root cause

`heartbeat_loop()` in `bot.py` proved liveness with a REST call:

```python
await client.fetch_user(client.user.id)
```

REST (`discord.com/api`) and the gateway websocket fail
independently. REST stayed healthy, so `/run/discord-claude/heartbeat`
kept refreshing, `watchdog.sh` saw a fresh heartbeat on all 84 ticks
of the outage and never restarted the unit.

## Change

`bot.py` — added `gateway_alive()` and gated the heartbeat on it.

```python
def gateway_alive() -> bool:
    if client.is_closed():
        return False
    ws = getattr(client, "ws", None)
    if ws is None or not ws.open:
        return False
    latency = client.latency
    return latency == latency  # NaN != NaN
```

`heartbeat_loop()` now raises before the REST call when
`gateway_alive()` is False, so the heartbeat file goes stale.

`DiscordWebSocket.open` is `not self.socket.closed` (discord.py
2.7.1, verified). `client.latency` is NaN when there is no session.

Backup: `bot.py.bak-20260901`.

## Effect

Stale heartbeat at `MAX_STALE=600` -> `watchdog.sh` runs
`systemctl restart discord-claude` -> discord.py backoff resets to
1s instead of sitting at 920s. Recovery tail drops from ~7h to
~10-12m.

A brief normal reconnect skips at most 1-2 heartbeats (120s each),
well under the 600s threshold, so no spurious restarts.

Known tradeoff: during a sustained Discord-side outage the watchdog
will bounce the unit roughly every 5-6 min. Harmless (no messages
are arriving to interrupt) but noisy in the journal.

## Not restarted

Change is on disk only. `systemctl restart discord-claude` pending
Gaurav's confirmation per the bot restart rule.
