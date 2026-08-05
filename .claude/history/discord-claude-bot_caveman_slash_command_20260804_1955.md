# /caveman as a real Discord slash command

**Date:** 2026-08-04 19:55 IST
**Files:** `bot.py`, `CLAUDE.md`

## Why the first attempt looked broken

Gaurav typed `/caveman wenyan-ultra` and got **"The application did not respond"** from an app
called **Rex** — the bot never saw the message at all.

Cause: `/name` in Discord is not chat text. It is dispatched to whichever *application* registers
that command, so `on_message` (and the `^[!/]?caveman ...` regex) never fires. Two apps are
installed in the guild `Laughing Coffin` (1150691625312456734):

- `Rex` — app id 1150692438940336171, owns a `caveman` command; its backend is the OpenClaw
  stack, removed 2026-07-09, so the interaction just times out
- `Claudy Rex` — app id 1508038405261361182, ours; verified via the API to have **no** global or
  guild commands at all

(Secondary point: the text handler wasn't live either — that change is still waiting on a restart.)

## Fix

Registered a genuine application command on our own app:

- `tree = discord.app_commands.CommandTree(client)`
- `/caveman [level]` with a `Choice` list: lite, full, ultra, wenyan-lite, wenyan-full,
  wenyan-ultra, off, default — the phone UI now shows a picker instead of free text
- handler gates on channel config + `ALLOWED_IDS`, then calls the shared `set_caveman()`
- `on_ready` does `copy_global_to(guild)` + `tree.sync(guild=...)` for every guild that holds a
  configured channel; guild syncs land immediately (global ones take ~1h)

`set_caveman(state, arg)` was factored out of the text handler, so `/caveman`, `!caveman` and a
bare `caveman` all run the same code and print the same reply.

## Verified

```
py_compile bot.py         OK
tree.get_commands()       ['caveman']
choices                   8 values, in order
set_caveman(None)         reports level + source
set_caveman("wenyan-ultra") / ("off") / ("default")   all correct
set_caveman("bogus")      rejected, lists valid values
app command inventory     Claudy Rex: none registered yet (sync happens at startup)
```

## Note on the collision

After the restart both apps will offer `/caveman` in the picker — ours (Claudy Rex) works, Rex's
is dead. Cleanest end state is removing the dead `Rex` app from the server, which is Gaurav's
call; flagged to him, not done.

## Not live

Needs `sudo systemctl restart discord-claude`. Until then `!caveman <level>` is the working form.
