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
- `DISCORD_CHANNEL_ID` — the default/main channel id, bound to the `__DEFAULT__` entry in `.claude/channels.json` (required)
- `DISCORD_ALLOWED_IDS` — comma-separated user IDs allowed to send tasks, shared across all channels (required)
- `PROJECTS_DIR` — root directory Claude runs tasks from for project-routing channels (default: `/home/gaurav/Projects`)
- `CLAUDE_BIN` — path to the `claude` CLI binary (default: `/home/gaurav/.local/bin/claude`)
- `TASK_TIMEOUT` — seconds before a task is killed (default: `600`)

## Multi-channel config (`.claude/channels.json`)

The bot listens on multiple Discord channels, each with its own working directory,
its own daily session/model/chat-history state, and its own extra "important points"
notes injected into every prompt. Defined as a JSON array in `.claude/channels.json`:

```json
[
  {"id": "__DEFAULT__", "name": "projects", "root_dir": null, "project_routing": true, "notes": ""},
  {"id": "1508034882645786644", "name": "obsidian", "root_dir": "/home/gaurav/Documents/ObsidianVault", "project_routing": false, "notes": "..."}
]
```

- `id` — Discord channel ID, or the literal string `"__DEFAULT__"` which resolves to `DISCORD_CHANNEL_ID` from `.env`.
- `root_dir` — fixed working directory for the channel. `null` means use `PROJECTS_DIR`.
- `project_routing` — if `true`, a leading `projectname: task` in the message routes into `root_dir/projectname` (falls back to `root_dir` if that subdir doesn't exist). If `false`, every message runs in `root_dir` as-is.
- `notes` — extra bullet appended to the "IMPORTANT POINTS TO REMEMBER" block for that channel only.

To add a new channel for a new project/folder, add another entry to this file — no code changes needed. Restart the service to pick up changes.

Per-channel state lives in `.claude/sessions/<channel_id>/` (session id, model override, chat history, prev-day summary) — fully isolated between channels.

## Architecture

The entire bot is a single file, `bot.py`. It bridges Discord messages to the `claude` CLI:

1. **Message gating** — `on_message` looks up the channel in `CHANNELS` (built from `channels.json`) and an allowlist of user IDs; unconfigured channels or disallowed users are ignored/rejected.
2. **Project routing** — `resolve_dir()` parses the `projectname: task` prefix syntax for channels with `project_routing` enabled. If the named subdirectory exists under the channel's `root_dir`, Claude runs there; otherwise it runs in `root_dir` itself.
3. **Task execution** — `run_claude()` spawns `claude --dangerously-skip-permissions -p <task>` as an async subprocess with a configurable timeout. Only one task runs at a time **per channel**; concurrent requests within the same channel are rejected until the user cancels, but different channels can run tasks simultaneously.
4. **Output delivery** — `send_long()` sends output ≤1900 chars inline in a code block; larger output is uploaded as `output.txt`.
5. **Cancellation** — each channel's `ChannelState.active_proc` / `active_task` track its running subprocess and asyncio task so `!cancel` in that channel kills both, without affecting other channels.
6. **Daily rollover** — `daily_rollover_loop()` fires once per day at 04:45 and rotates/summarizes every configured channel's session independently.

Built-in bot commands (per-channel): `!help`, `!projects`, `!cancel` / `!stop`, `!status`, `!session`, `!newsession`, `model <name>`.
