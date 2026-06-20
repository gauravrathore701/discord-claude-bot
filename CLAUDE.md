# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in values
```

Two venvs exist (`venv/` and `.venv/`); the systemd service uses `venv/`.

## Running

```bash
source venv/bin/activate
python bot.py
```

Service management (runs as `gaurav` on this Pi):
```bash
sudo systemctl start discord-claude
sudo systemctl status discord-claude
sudo journalctl -u discord-claude -f   # live logs
```

## Environment Variables

Defined in `.env` (see `.env.example`):
- `DISCORD_TOKEN` — bot token (required)
- `DISCORD_CHANNEL_ID` — the single channel the bot listens on (required)
- `DISCORD_ALLOWED_IDS` — comma-separated user IDs allowed to send tasks (required)
- `PROJECTS_DIR` — root directory Claude runs tasks from (default: `/home/gaurav/Projects`)
- `CLAUDE_BIN` — path to the `claude` CLI binary (default: `/home/gaurav/.local/bin/claude`)
- `TASK_TIMEOUT` — seconds before a task is killed (default: `600`)

## Architecture

The entire bot is a single file, `bot.py`. It bridges Discord messages to the `claude` CLI:

1. **Message gating** — `on_message` filters to one channel and an allowlist of user IDs; all other messages are silently ignored or rejected.
2. **Project routing** — `resolve_dir()` parses the `projectname: task` prefix syntax. If the named subdirectory exists under `PROJECTS_DIR`, Claude runs there; otherwise it runs in `PROJECTS_DIR` itself.
3. **Task execution** — `run_claude()` spawns `claude --dangerously-skip-permissions -p <task>` as an async subprocess with a configurable timeout. Only one task runs at a time; concurrent requests are rejected until the user cancels.
4. **Output delivery** — `send_long()` sends output ≤1900 chars inline in a code block; larger output is uploaded as `output.txt`.
5. **Cancellation** — `active_proc` and `active_task` globals track the running subprocess and asyncio task so `!cancel` can kill both.

Built-in bot commands: `!help`, `!projects`, `!cancel` / `!stop`, `!status`.
