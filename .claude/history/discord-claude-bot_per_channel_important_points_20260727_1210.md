# Per-channel IMPORTANT POINTS block

Date: 2026-07-27 12:10

## Goal

Make the "IMPORTANT POINTS TO REMEMBER" block injected into every prompt vary per Discord channel.

## Before

`run_claude()` hardcoded 8 base bullets inline, then appended `cfg.notes` as a single extra
bullet (`- {cfg.notes}\n`). Per-channel variation was additive only — no way to drop or replace
a base point, and multi-bullet notes required embedding `\n-` inside one JSON string.

## After

- `BASE_POINTS: dict[str, str]` — the 8 shared bullets, keyed: `session`, `recall`, `internet`,
  `history`, `profile`, `personality`, `restart`, `media`.
- `build_points_block(cfg)` — assembles `(BASE_POINTS - cfg.omit) + cfg.notes`. Returns `""`
  (no header) when a channel resolves to zero bullets.
- `ChannelConfig.notes` is now `list[str]`; `load_channels()` accepts a JSON string (wrapped to
  a 1-element list) or a JSON list, so existing `channels.json` works unchanged.
- New `ChannelConfig.omit: list[str]` — base keys to drop for that channel.
- New `ChannelConfig.replace_points: bool` — skip base points entirely, use only `notes`.
- New `!points` command prints the channel's resolved block; listed in `!help`.
- `run_claude()` now just calls `build_points_block(cfg)`.

## Files changed

- `bot.py` — config dataclass, `BASE_POINTS`, `build_points_block()`, `load_channels()`,
  `run_claude()`, `!points` command, `!help` text.
- `CLAUDE.md` — documented `notes` as string-or-list, `omit`, `replace_points`, `!points`.
- `.claude/channels.json` — untouched; behavior identical to before.

## Verification

Executed the config section standalone against the live `channels.json`: both channels resolve
to 9 bullets (8 base + 1 note) — byte-identical intent to the old hardcoded block. Also tested
`omit` (drops the named base points), `replace_points` (notes only), and the empty case
(returns `""`, no dangling header).

Not restarted — awaiting confirmation per BOT RESTART RULE.
