# Vault channel replied with only "Note + log written"

**Date:** 2026-08-28 18:30 IST

## Symptom
In rex-chat (channel id 1508034882645786644, labeled
"obsidian" in channels.json, root_dir
/home/gaurav/Documents/ObsidianVault) the bot answered a real
question with just `Note + log written.` — no answer text.

## Cause
Prompt, not code. That channel carries 5 AUTO-DOCUMENT notes
telling the model to write a vault note and report the path.
Combined with caveman ULTRA, the model treated the note as the
deliverable and the Discord reply as a status line. Nothing in
bot.py truncates output.

## Fix
`.claude/channels.json` — prepended an ANSWER FIRST note to that
channel's `notes` list (now 6 entries, new one is index 0):
reply is the deliverable, vault note is a side-effect; never
reply with only "Note written"/path/status; full answer in the
message even when saved; note path last as one short line.

No code change. No other channel touched.

## Deploy
channels.json is read once at import (bot.py:241), so a restart
was required. build_points_block() runs per message (bot.py:573),
so no session reset was needed. Restarted discord-claude.
