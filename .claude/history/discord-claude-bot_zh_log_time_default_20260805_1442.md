# zh-ai-support: default log search window = last 1 hour

Date: 2026-08-05 14:42

## Why

Unbounded log searches on zh-ai-support were scanning huge ranges — slow, and the
main reason tasks hit the task timeout. Gaurav wants an implicit 1h window when he
doesn't name one.

## Change — .claude/channels.json

New note (second-to-last) on the zh-ai-support channel, injected into every prompt
via `build_points_block()`:

> LOG TIME RANGE DEFAULT: if I don't mention a time window for a log search,
> search the LAST ONE HOUR only (now-1h to now). Never widen it on your own — if
> one hour returns nothing or too little, say so and ask before searching a longer
> range, and always state the exact window you searched in the answer.

No code change. Pairs with the 25m per-channel timeout added earlier today
(`discord-claude-bot_per_channel_timeout_20260805_1435.md`).

## Verified

```
channels.json parse   OK
zh-ai-support notes   12 (was 11)
timeout               1500s
points block          4673 chars,
                      contains the new bullet
```

Requires `sudo systemctl restart discord-claude`.
