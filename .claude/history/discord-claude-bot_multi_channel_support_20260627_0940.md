# Multi-channel support

Refactored the bot from a single hardcoded `DISCORD_CHANNEL_ID` to support
multiple Discord channels, each independently configured and stateful.

## What changed

- New `.claude/channels.json` — array of channel configs: `id` (or `"__DEFAULT__"`
  to bind to `DISCORD_CHANNEL_ID` from `.env`), `name`, `root_dir` (fixed cwd, or
  `null` to use `PROJECTS_DIR`), `project_routing` (enable/disable the
  `projectname: task` prefix), and `notes` (extra per-channel instructions
  appended to the prompt's "IMPORTANT POINTS TO REMEMBER" block).
- Added a second channel: id `1508034882645786644`, name `obsidian`, rooted at
  `/home/gaurav/Documents/ObsidianVault`, `project_routing: false`, with notes
  telling Claude to treat the vault as primary context for that channel.
- All previously-global mutable state (`_session_id`, `_model`, `active_proc`,
  `active_task`, etc.) moved into a `ChannelState` dataclass, one instance per
  configured channel, so sessions/models/history/active-task tracking are fully
  isolated per channel. Two channels can now run tasks concurrently; only
  same-channel concurrency is blocked.
- Per-channel persistent state (`current.json`, `model.json`,
  `chat_history.json`, `prev_summary.json`) moved from `.claude/sessions/` to
  `.claude/sessions/<channel_id>/`. Migrated the existing default channel's
  files into `.claude/sessions/1508034842304970772/`.
- `daily_rollover_loop()` now iterates all configured channels at 04:45,
  retrying only the channels still mid-task rather than blocking globally.
- `on_ready()` posts the online message to every configured channel.
- Updated `.claude/sessions/.gitignore` to glob-ignore state files one level
  down (`*/current.json` etc.) instead of flat filenames.
- Documented the new config format and per-channel architecture in `CLAUDE.md`.

## Why

Gaurav wants a second Discord channel dedicated to chatting against his
Obsidian vault contents, separate from the project-task channel, and wants the
ability to add more project/folder-scoped channels in the future without code
changes — just a new `channels.json` entry.

## Not yet done

- Changes are committed locally but not pushed, and the systemd service hasn't
  been restarted to pick up the new code — both need explicit go-ahead since
  this bot process serves the conversation that made the change.
