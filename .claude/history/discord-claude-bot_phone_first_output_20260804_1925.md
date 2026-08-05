# Phone-first output: 45-char budget + table demotion

**Date:** 2026-08-04 19:25 IST
**Files:** `bot.py`, `CLAUDE.md`

## Ask

Gaurav reads Discord almost entirely on his phone — **Poco X4 Pro 5G**, 6.67", 1080x2400.
Answers must render correctly there.

Measured constraint: a Discord code block on that screen shows about **45 monospace characters**
before it scrolls sideways; a wider line is simply cut off in view.

## 1. `discord_format` base point rewritten (all channels)

Now phone-specific, with a hard budget:

- no line inside a ``` block over **45 chars** — break commands with a trailing `\`, split long
  paths/URLs, shorten sample output rather than pasting wide
- never `|` tables; 2 columns -> `label — value` bullets; 3+ -> narrow code block, else one block
  per row
- `**bold**` labels over `##` headers (headers eat vertical space), 2-3 sections max
- short lines, short paragraphs, no deep nesting
- aim well under 1900 chars; lead with the answer

## 2. The point alone was not enough

Live test: asked for a caveman level comparison. The model emitted a `|` markdown table anyway —
the injected caveman SKILL.md **itself contains** an intensity table, so the example bleeds through.

Added a deterministic pass, `demote_tables(text)`, run in `send_long()` before splitting:

- finds pipe tables outside code fences (header row + `|---|` separator)
- total width ≤ `PHONE_WIDTH` (45) -> aligned code block with a dashed rule
- wider -> per-row block:

```
**lite**
- What changes — No filler/hedging.
- Example — "Your component re-renders ..."
```

Nothing is truncated; wide content just becomes vertical. Tables inside code fences are left alone.

## 3. `MAX_CHUNKS` 6 -> 10

A file attachment is the worst thing to read on a phone, so the bot now prefers a few more
messages before falling back to `answer.md`.

## Verified

```
py_compile bot.py                     OK
wide table   -> per-row bold blocks, no truncation
narrow table -> aligned code block, 4 lines
table inside a code fence             untouched
text with no table                    byte-identical passthrough
live haiku run, table-prone prompt:
  raw output       5 pipe lines
  after demote     0 pipe lines
  widest code line 42 and 44 (budget 45) across two runs
  1 chunk, 692 chars
```

## Not live

Needs `sudo systemctl restart discord-claude` — waiting on Gaurav's yes per the BOT RESTART RULE.
