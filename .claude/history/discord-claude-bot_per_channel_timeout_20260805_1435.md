# Per-channel task timeout

Date: 2026-08-05 14:35

## Why

zh-ai-support tasks (Elasticsearch log sweeps across connectors/clients) exceed the
global `TASK_TIMEOUT=600`. A live task died with "Timed out after 600s." Gaurav asked
for a channel-scoped limit of 25 minutes instead of raising it everywhere.

## Changes — bot.py

- `ChannelConfig.timeout: int | None` — seconds, `None` => `TASK_TIMEOUT`.
- `parse_timeout(entry)` — reads `timeout_minutes` (wins) or `timeout`, accepting
  int seconds, `"1500"`, `"25m"`, `"90s"`. Clamped to >= 1s.
- `fmt_secs(secs)` — `1500 -> 25m`, `95 -> 1m35s`.
- `channel_timeout(cfg)` — `cfg.timeout or TIMEOUT`.
- `load_channels()` populates `timeout=parse_timeout(entry)`.
- `run_claude()` uses `limit = channel_timeout(cfg)` for `asyncio.wait_for`; the
  timeout message now names the limit and channel:
  `Timed out after 1500s (25m, zh-ai-support channel limit).`
- `!status` prints `Timeout: 25m (1500s, channel|default)`.
- Startup log lists `(id, name, timeout)` per channel.

## Changes — .claude/channels.json

zh-ai-support entry gains `"timeout_minutes": 25`. Other channels unchanged (600s).

## Verified

```
py_compile                  OK
projects        600  10m  default
obsidian        600  10m  default
zh-ai-support  1500  25m  override
parse_timeout   25min/"25m"/1500/"90s"/{} ->
                1500/1500/1500/90/None
fmt_secs        1500=25m 600=10m 95=1m35s
```

## Docs

CLAUDE.md — `TASK_TIMEOUT` env line + new `timeout_minutes` bullet in the
channels.json field list.

Requires `sudo systemctl restart discord-claude` to take effect.
