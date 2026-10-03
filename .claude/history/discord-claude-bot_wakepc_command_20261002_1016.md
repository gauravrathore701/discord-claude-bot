# !wakepc — wake the main PC from Discord

2026-10-02 10:16

## What changed

`ops.py` gained a `wakepc()` handler, wired to `!wakepc` (alias `!wake`)
and listed in `HELP`. Native ops command — runs locally in the bot
process, no Claude call, no tokens.

Backup of the original: `ops.py.bak-20261002`.

New module constants:

```python
WOL_SCRIPT  = ".../daily-script/wol_pc.sh"
WOL_TIMEOUT = 120   # script gives up at 90s
PC_IP       = "192.168.50.2"
```

## Behaviour

- Runs `wol_pc.sh`, which arpings the PC first and returns straight
  away if it is already awake.
- Otherwise fires the magic packet and polls for up to 90s.
- Replies: already-awake, success with the script's timing line, or a
  failure block with the script output.
- `subprocess.TimeoutExpired` and `OSError` are both caught, so a
  hung script can't take the bot down with it.

## Why no sudo

`arping` needs a raw socket. Rather than a sudoers entry, the binary
was given the capability directly:

```
sudo setcap cap_net_raw+ep /usr/bin/arping
```

The bot runs as `gaurav` and calls the script unprivileged.

## Verified

```
python3 -c "import ops; print(ops.handle('!wakepc'))"
-> '✅ Already awake — 192.168.50.2 is answering.'
```

Unknown commands still return `None` (fall through to Claude).

**Not yet live** — needs `systemctl restart discord-claude` to load.

## Context

Full Wake-on-LAN setup, topology and the open 100 Mb/s link issue are
documented in `daily-script/.claude/history/
daily-script_wol_pc_setup_20261002_1016.md`.
