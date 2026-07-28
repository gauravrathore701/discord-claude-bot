# Obsidian channel — auto-document rule

Date: 2026-07-27 21:30

## Goal

In the `obsidian` Discord channel, Claude should document answers into the vault on its own —
any question about a person, technical topic, or anything worth remembering — without Gaurav
having to ask for it each time.

## Change

`.claude/channels.json` — obsidian entry's `notes` converted from a single string to a list of
5 bullets (enabled by the list-notes support added in
`discord-claude-bot_per_channel_important_points_20260727_1210.md`):

1. (existing) vault is the primary context for this channel
2. **AUTO-DOCUMENT EVERYTHING** — write substantive answers into the vault unprompted
3. **WHERE** — routing map to existing folders: people -> `Mobile/People/<Name>.md`,
   technical -> `Main/StudyNotesTechnical/`, AI/LLM -> `Main/AI/`, shell -> `Main/LinuxCommands/`
   or `Main/GeneralUtils/`, work -> `Office/<domain>/`, markets -> `Main/ShareMarketStudies/` or
   `Main/Trading/`; read the vault's own `CLAUDE.md` for the full map before deciding
4. **HOW** — append a dated section to an existing note rather than duplicating; new notes use
   the `Templates/Default.md` `**Tags:**` header; distilled facts not transcripts; `[[wikilinks]]`;
   report the path written
5. **SKIP** — greetings, one-word replies, `!`-commands, bot/vault plumbing questions, and
   anything Gaurav says not to save

Folder targets were taken from the live vault layout (`Main/`, `Mobile/People/`, `Office/`,
`DailyNotes/`, `Templates/`) and its `CLAUDE.md`, not invented.

## Verification

Rendered both channels' blocks from the live JSON: `obsidian` -> 13 bullets (8 base + 5 notes),
`projects` -> 9 bullets, unchanged. JSON parses clean.

No `bot.py` change needed. Not restarted — awaiting confirmation per BOT RESTART RULE.
