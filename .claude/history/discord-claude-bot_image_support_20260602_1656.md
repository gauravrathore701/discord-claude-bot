# discord-claude-bot: Image Attachment Support

**Date:** 2026-06-02 16:56 IST

## What Was Done

Added support for reading images sent via Discord messages.

## Changes to `bot.py`

1. Added `import tempfile` to imports.

2. In `on_message`, replaced the `if not text: return` guard with:
   - Detect image attachments (`message.attachments` filtered by `content_type.startswith("image/")`)
   - Return early only if BOTH text and image attachments are absent

3. Before task dispatch: download each image attachment to a temp file (`/tmp/discord_img_*.<ext>`), append `[Image attached — read this file with your Read tool: <path>]` lines to the task prompt.

4. If message is image-only (no text), prompt becomes: `"The user sent an image. Read it and respond:\n[Image file: ...]"`

5. In `do_task()` finally block: clean up all temp image files with `os.unlink()`.

## Supported formats

Detects any `image/*` content type; saves with original extension if it's png/jpg/jpeg/gif/webp, otherwise defaults to `.png`.

## Note

Multiple "Claude Code bot is online" messages appeared in Discord channel during this session — caused by 4 manual service restarts while debugging a sudo permission issue (exit code 144). Not a bot malfunction.
