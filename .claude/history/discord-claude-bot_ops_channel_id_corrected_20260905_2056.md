# pi-ops channel ID corrected — 2026-09-05 20:56

## What went wrong
The channel ID Gaurav supplied for the ops channel,
`1537133272319008798`, resolves to **#claudy-logs**, not
#claudy-cmds. I wired `pi-ops` to it without checking the
name against Discord, so `!usage` and a plain `hii` in
#claudy-cmds both got no reply — the bot was not listening
there.

Resolved via the Discord API with the bot token:

```
1537133272319008798  #claudy-logs
1545758605465100449  #claudy-cmds
1545733400873271356  #blog-discussion
```

The blog channel ID was correct; only the ops one was wrong.

## Why it mattered more than a typo
#claudy-logs is the target of the NetworkManager IP-change
dispatcher. Left as configured, every log post into that
channel would have been treated as a task and answered by
the model, spending tokens on machine-generated messages.

## Fix
`pi-ops` entry repointed to `1545758605465100449`. The
seeded session state (`model.json` -> haiku,
`caveman.json` -> full) copied to the new session dir.
Backup: `.claude/channels.json.bak2-20260905`.

Restart scheduled detached at 20:56:39 IST via
`systemd-run --on-active=60`.

## Note for future channel work
Always resolve a supplied channel ID to its name through
`GET /channels/<id>` before writing it into channels.json.
One API call would have caught this immediately.

## Unrelated, worth recording
The `/usage` and `/caveman` slash commands Gaurav saw in the
picker belong to the **old Rex bot**, a separate Discord
application. Its "The application did not respond" error is
not this bot. discord-claude registers only `/caveman`; all
its other commands are `!`-prefixed.
