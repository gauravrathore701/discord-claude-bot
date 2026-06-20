# discord-claude-bot — Model Switch Command

**Date:** 2026-06-11

## What Was Done

Added a model-switching feature to `bot.py`:

- **New command:** `model <sonnet|opus|haiku|fable|default>` (also works as `!model`).
  - No argument → shows the current model.
  - `model default` → clears the override (falls back to `~/.claude/settings.json`, currently `claude-fable-5`).
- **Persistence:** choice saved to `.claude/sessions/model.json`, loaded on bot startup — survives restarts and daily session resets.
- **Wiring:** `run_claude()` now appends `--model <alias>` to the claude CLI invocation when an override is set. Applies from the next message (sessions keep their history via `--resume`; the model flag just changes which model serves the turn).
- `!help` updated to document the command.

## Implementation Notes

- `MODEL_ALIASES = {"sonnet", "opus", "haiku", "fable"}` — CLI accepts these aliases directly (maps to latest of each tier).
- Command regex: `^!?model(?:\s+(\S+))?$` — matches both `model fable` and `!model fable`.
- Service restarted at 16:12 IST to load changes. Note: restarting `discord-claude` kills any in-flight claude subprocess (the bot runs claude as a child process) — the restart command itself died with exit 144 for this reason, but the restart succeeded.

## Related Earlier Change (same day)

- Claude Code CLI updated 2.1.150 → 2.1.173; default model set to `claude-fable-5` in `~/.claude/settings.json` (see `~/.claude/history/claudecode_update_fable5_20260611_1300.md`).
