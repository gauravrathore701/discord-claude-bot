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
- `TASK_TIMEOUT` — seconds before a task is killed (default: `600`); a channel can override it with `timeout_minutes` / `timeout` in `channels.json`
- `CAVEMAN_SKILL_FILE` — path to the `/caveman` SKILL.md injected into every task (default: `/home/gaurav/.claude/skills/caveman/SKILL.md`)
- `CAVEMAN_LEVEL` — intensity the skill is pinned to (default: `ultra`; `off` disables the injection)

## Multi-channel config (`.claude/channels.json`)

The bot listens on multiple Discord channels, each with its own working directory,
its own daily session/model/chat-history state, and its own extra "important points"
notes injected into every prompt. Defined as a JSON array in `.claude/channels.json`:

```json
[
  {"id": "__DEFAULT__", "name": "projects", "root_dir": null, "project_routing": true, "notes": ""},
  {"id": "1508034882645786644", "name": "obsidian", "root_dir": "/home/gaurav/Documents/ObsidianVault",
   "project_routing": false, "notes": ["...", "..."], "omit": ["history"], "replace_points": false},
  {"id": "1528641869637095444", "name": "zh-ai-support", "root_dir": "/home/gaurav/Projects/zh-ai-support",
   "project_routing": false, "notes": ["...", "..."]}
]
```

The `zh-ai-support` channel carries that project's own IMPORTANT POINTS (index/account config
files, `.claude/docs`, `.claude/skills`, `config/LOG_INFO.md`) as its `notes`, on top of the
shared base points. Same shape as the obsidian channel — a channel bound to one folder.

- `id` — Discord channel ID, or the literal string `"__DEFAULT__"` which resolves to `DISCORD_CHANNEL_ID` from `.env`.
- `root_dir` — fixed working directory for the channel. `null` means use `PROJECTS_DIR`.
- `project_routing` — if `true`, a leading `projectname: task` in the message routes into `root_dir/projectname` (falls back to `root_dir` if that subdir doesn't exist). If `false`, every message runs in `root_dir` as-is.
- `notes` — extra bullets appended to the "IMPORTANT POINTS TO REMEMBER" block for that channel only. Either a single string (one bullet) or a list of strings (one bullet each).
- `omit` — list of `BASE_POINTS` keys to drop for this channel. Valid keys: `session`, `recall`, `internet`, `history`, `profile`, `personality`, `restart`, `discord_format`. Default `[]`.
- `replace_points` — if `true`, all shared base points are skipped and only `notes` are injected. Default `false`.
- `timeout_minutes` / `timeout` — per-channel task timeout. `"timeout_minutes": 25`, `"timeout": 1500` (seconds) and `"timeout": "25m"` / `"90s"` all work; `timeout_minutes` wins if both are set. Omitted -> `TASK_TIMEOUT` from `.env`. `run_claude()` uses `channel_timeout(cfg)`, so a long zh-ai-support log analysis can run 25m while other channels still cap at 10m. `!status` prints the resolved value and whether it came from the channel or the default, and the startup log lists `(id, name, timeout)` per channel.

### The shared points block

`BASE_POINTS` in `bot.py` is an ordered dict of `key -> bullet text`; `build_points_block(cfg)`
assembles each channel's block as (base points minus `omit`) + `notes`. If a channel ends up
with zero bullets the header is omitted entirely. `!points` in any channel prints that
channel's resolved block for verification.

To add a new channel for a new project/folder, add another entry to this file — no code changes needed. Restart the service to pick up changes.

Per-channel state lives in `.claude/sessions/<channel_id>/` (session id, model override, chat history, prev-day summary) — fully isolated between channels.

## Architecture

The entire bot is a single file, `bot.py`. It bridges Discord messages to the `claude` CLI:

1. **Message gating** — `on_message` looks up the channel in `CHANNELS` (built from `channels.json`) and an allowlist of user IDs; unconfigured channels or disallowed users are ignored/rejected.
2. **Project routing** — `resolve_dir()` parses the `projectname: task` prefix syntax for channels with `project_routing` enabled. If the named subdirectory exists under the channel's `root_dir`, Claude runs there; otherwise it runs in `root_dir` itself.
3. **Task execution** — `run_claude()` spawns `claude --dangerously-skip-permissions -p <task>` as an async subprocess with a configurable timeout. `caveman_prompt(level)` reads the `/caveman` SKILL.md (frontmatter stripped, cached per level), wraps it in an "active at `<level>`" preamble, and every task passes the channel's level via `--append-system-prompt` — the real skill, not a paraphrase, on all channels. Only one task runs at a time **per channel**; concurrent requests within the same channel are rejected until the user cancels, but different channels can run tasks simultaneously.
4. **Output delivery** — written for Discord **mobile** (Gaurav reads on a Poco X4 Pro 5G; `PHONE_WIDTH = 45` monospace chars fit in a code block before it scrolls sideways).
   - `demote_tables()` rewrites every `|` markdown table outside code fences — Discord renders none of them. Narrow enough (≤ `PHONE_WIDTH`) -> aligned code block; wider -> one `**row label**` + `- column — value` block per row, so nothing is cut off.
   - `split_for_discord()` then cuts on line boundaries into ≤1900-char chunks, closing and re-opening any ``` fence that straddles a boundary.
   - `send_long()` posts the chunks as plain markdown. More than `MAX_CHUNKS` (10) chunks -> first chunk inline plus the full text as `answer.md`; the limit is deliberately high because file attachments read badly on a phone.
   - The `discord_format` base point tells Claude to write for the same target: 45-char cap inside code blocks, no `|` tables, `**bold**` labels over `##` headers, short lines, well under 1900 chars.
5. **Cancellation** — each channel's `ChannelState.active_proc` / `active_task` track its running subprocess and asyncio task so `!cancel` in that channel kills both, without affecting other channels.
6. **Daily rollover** — `daily_rollover_loop()` fires once per day at 04:45 and rotates/summarizes every configured channel's session independently.

Built-in bot commands (per-channel): `!help`, `!projects`, `!points`, `!cancel` / `!stop`, `!status`, `!session`, `!newsession`, `model <name>`, `/caveman <level>`.

## Caveman level

`caveman_prompt(level)` builds the `--append-system-prompt` text from `CAVEMAN_SKILL_FILE`
(cached per level). Each channel's level is `ChannelState.caveman or CAVEMAN_LEVEL`, so the
`.env` value is only a default — `/caveman <level>` sets it for that channel and persists to
`.claude/sessions/<channel_id>/caveman.json`. `/caveman` is a real Discord application command
(`discord.app_commands.CommandTree`, synced per guild in `on_ready` — guild syncs are instant,
global ones take ~1h) because a `/name` typed in Discord is dispatched to whichever app owns that
command and never reaches `on_message`. `!caveman <level>` and a bare `caveman <level>` go through
the text handler; all three call the same `set_caveman()`. Valid levels:
`lite`, `full`, `ultra`, `wenyan-lite`, `wenyan-full`, `wenyan-ultra`, plus `off` (no skill
injected at all) and `default` (fall back to `CAVEMAN_LEVEL`). No argument prints the current
level and where it came from.
