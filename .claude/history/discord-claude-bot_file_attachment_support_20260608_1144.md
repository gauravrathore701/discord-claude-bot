# discord-claude-bot: File Attachment Support
**Date:** 2026-06-08 11:44

## What was done
Added support for non-image file attachments (scripts, text files, etc.) sent via Discord.

## Changes — `bot.py`
- Added `file_attachments` list: any attachment that isn't an image
- Download file attachments to `/tmp/` using `tempfile.NamedTemporaryFile` with the original filename as suffix (e.g. `discord_file_myscript.py`)
- Inject note into Claude prompt: `[File attached: 'filename.py' — read it with your Read tool at path: /tmp/...]`
- Cleanup: temp files are deleted after the task completes (in the `finally` block)

## Why
Gaurav wanted to send script files from Discord and have Claudy Rex read and act on them — same flow as images, just for text/script files.

## Test
Send any `.py`, `.sh`, `.js`, etc. file as a Discord attachment. Bot will download it and Claude will read it via the Read tool.
