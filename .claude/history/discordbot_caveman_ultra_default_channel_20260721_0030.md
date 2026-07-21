# discord-claude-bot — caveman-ultra forced on default channel (2026-07-21 00:30)

## What

Channel `1508034842304970772` (= `__DEFAULT__`, the main projects channel bound
to `DISCORD_CHANNEL_ID`) now always replies in CAVEMAN ULTRA style.

## How

No code change. Set `notes` on the `__DEFAULT__` entry in
`.claude/channels.json` to the caveman-ultra instruction. `run_claude()`
appends each channel's `notes` to the "IMPORTANT POINTS TO REMEMBER" block on
every prompt, so this persists across every turn in that channel without a skill
invocation.

The instruction encodes the caveman skill's ultra rules inline: keep all
technical substance, drop articles/filler/pleasantries/hedging, abbreviate prose
words + arrows for causality, and explicitly EXEMPT code / function names / API
names / file paths / commands / error strings / commit messages / PR bodies
(stay exact) + drop caveman for security warnings and irreversible-action
confirmations.

## Activation

Only picked up on `load_channels()` at startup → requires
`systemctl restart discord-claude`. Pending Gaurav's confirmation per the bot
restart rule.

## Note

Other channels unaffected (obsidian keeps its own notes; empty-notes channels
reply normally).
