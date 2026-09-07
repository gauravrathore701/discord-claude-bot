# .bak files moved to backups/ and untracked — 2026-09-06 13:10

## Why
All 7 pre-edit backups were tracked by git, and this repo
is public (api.github.com -> "visibility": "public").
.gitignore covered .env / venv / *.env but had no *.bak
rule, so every backup I made was published by the 08:00
sync.

Scanned before acting: no credentials in any of them.
Every copy reads TOKEN = os.environ["DISCORD_TOKEN"].
The channels.json backups hold the same channel IDs as
the tracked live file, so nothing new was exposed.

## Moved to backups/ (7 files, ~166 KB)
    bot.py.bak-20260901
    bot.py.bak-20260902
    bot.py.bak-20260905
    watchdog.sh.bak-20260830
    channels.json.bak.20260812
    channels.json.bak-20260905
    channels.json.bak2-20260905
The three channels.json copies came from .claude/;
the rest from the repo root. Also parked there:
    .gitignore.bak-20260906

## .gitignore additions
    backups/
    *.bak
    *.bak-*
    *.bak.*
    *.bak2-*
Both the folder and the patterns, so a stray backup left
outside backups/ still will not publish.

## Git state
`git rm --cached` on all 7 — index only, files kept on
disk. Staged as 7 deletions plus the .gitignore edit,
left uncommitted; the 08:00 sync will commit and push,
which is what removes them from the public tree.

IMPORTANT: this does not erase them from GitHub history.
Past commits still contain every one. Removing them from
history means a rewrite + force push, which was NOT done
and needs Gaurav's explicit go-ahead. Given no secrets
were found, there is no urgency.

## Verified
    bot.py, watchdog.sh, .claude/channels.json  intact
    no code references any .bak path
      (only hit is the deletion-rule text in bot.py:144)
    git check-ignore  -> backups/ matched
    git status        -> backups/ not listed, correctly
                         ignored
    discord-claude.service  active, not restarted
