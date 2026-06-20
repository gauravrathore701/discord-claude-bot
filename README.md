# Discord Claude Bot

A Discord bot that acts as a remote control interface for the Raspberry Pi. It bridges Discord messages to the Claude Code CLI, letting you run engineering tasks, manage projects, and interact with the Pi — all from Discord.

---

## How It Works

1. You send a message in the configured Discord channel
2. The bot passes it to `claude` (Claude Code CLI) as a prompt
3. Claude executes — reads files, runs shell commands, edits code, etc.
4. The response is chunked and sent back to Discord (respects the 1900-char limit)

The bot maintains a daily session (resets at **04:45 AM IST**) and injects context from the previous session's last 5 exchanges to preserve continuity.

## Features

- Full Claude Code CLI access from Discord
- Session continuity across messages (chat history kept per day)
- Configurable model per session: `model sonnet|opus|haiku|fable|default`
- "Still working..." ping every 2 minutes for long tasks
- Only responds to whitelisted Discord user IDs

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13 |
| Discord Library | discord.py |
| AI Backend | Claude Code CLI (`~/.local/bin/claude`) |
| Process Handling | asyncio subprocess |

## Configuration (`.env`)

```env
DISCORD_TOKEN=<bot token>
DISCORD_CHANNEL_ID=<channel id>
DISCORD_ALLOWED_IDS=<user1_id>,<user2_id>
PROJECTS_DIR=/home/gaurav/Projects
CLAUDE_BIN=/home/gaurav/.local/bin/claude
TASK_TIMEOUT=600
```

## Running

```bash
pip install -r requirements.txt
python bot.py
```

## Deployment

```bash
sudo systemctl status discord-claude
sudo systemctl restart discord-claude
```

Runs as `discord-claude.service` on the Pi (24/7).
