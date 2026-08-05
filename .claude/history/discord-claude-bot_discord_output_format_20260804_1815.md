# Discord-shaped output: format point + markdown-preserving chunker

**Date:** 2026-08-04 18:15 IST
**Files:** `bot.py`, `CLAUDE.md`

## Complaint

Answers arrive as `.md` file uploads containing markdown tables that Discord doesn't render.
Gaurav asked for a shared important-point for every channel of this bot: *"give output in a
format that looks good on discord chat"*.

Two separate causes, both fixed.

## 1. New base point `discord_format`

Added to `BASE_POINTS` in `bot.py`, so it lands in every channel's block (droppable per channel
via `"omit": ["discord_format"]`). Tells Claude: reply goes straight into a Discord chat; no `|`
markdown tables — Discord doesn't render them; tabular data in a ``` code block with aligned
columns or `label — value` bullets; bold labels, short lines, sparing `##`; keep under ~1900
chars or it gets split/attached; lead with the answer.

Bullet counts after the change: projects 9, obsidian 13, zh-ai-support 19.

## 2. The bot was destroying its own markdown

`send_long()` wrapped **every** chunk in a ``` fence, so nothing rendered — headers, bold,
tables all showed as literal source — and it split at a fixed 1892 chars, mid-line and mid-fence.

Replaced with `split_for_discord(text, limit=1900)`:

- splits on line boundaries, never mid-line (a single over-long line is still hard-cut)
- tracks the open ``` fence; if one straddles a boundary it is closed at the end of the chunk
  and re-opened (with its language tag) at the top of the next
- returns raw markdown — no wrapper fence, so Discord renders it

`send_long()` now posts those chunks as-is. Over `MAX_CHUNKS = 6` chunks -> first chunk inline
plus the full text attached as `answer.md` (temp file, unlinked after send).

## Verified

```
py_compile bot.py                          OK
short markdown                             1 chunk, unwrapped, byte-identical to input
400-line fenced block + trailing text      2 chunks, fences balanced in both,
                                           chunk1 ends ```, chunk2 starts ```python, tail kept
5000-char single line                      3 chunks, max len 1892
300 random lines                           24 chunks, all <=1900, no lines lost
empty string                               ['']
points block                               projects 9 / obsidian 13 / zh-ai-support 19
```

## Not live

Needs `sudo systemctl restart discord-claude` — asked Gaurav, waiting on his yes per the
BOT RESTART RULE.
