# /caveman ultra injected as a real skill on every task

**Date:** 2026-08-04 19:05 IST
**Files:** `bot.py`, `.claude/channels.json`, `CLAUDE.md`

## Ask

Gaurav: discord-claude chats should run the **actual `/caveman ultra` skill** for every task,
not the hand-written style paragraph that was sitting in the points block.

## How

`claude` CLI has `--append-system-prompt`. `bot.py` now reads the skill file once at import:

```python
CAVEMAN_SKILL_FILE = os.environ.get("CAVEMAN_SKILL_FILE",
                                    "/home/gaurav/.claude/skills/caveman/SKILL.md")
CAVEMAN_LEVEL      = os.environ.get("CAVEMAN_LEVEL", "ultra")

def load_caveman_prompt() -> str:   # frontmatter stripped, wrapped in an "ACTIVE at <level>" preamble
    ...

CAVEMAN_PROMPT = load_caveman_prompt()
```

and every task carries it:

```python
if CAVEMAN_PROMPT:
    cmd += ["--append-system-prompt", CAVEMAN_PROMPT]
```

3605 chars. Applies to **all** channels — projects, obsidian, zh-ai-support. `CAVEMAN_LEVEL=off`
or a missing file disables it (logged, no crash). `on_ready` prints the level, size and path.

Chose the system prompt over making the model call the Skill tool per task: deterministic, no
extra turn, no dependence on the model deciding to invoke it.

## Points block trimmed

The `__DEFAULT__` channel's `notes` in `channels.json` held a ~1.5 KB paraphrase of the same
rules. Replaced with a short bullet that says the skill is already loaded at ULTRA and lists
the sub-skills (caveman-commit / review / compress / stats / help, cavecrew). Net token change
is roughly a wash but the rules now have exactly one source: the skill file.

## Verified

```
py_compile bot.py                         OK
CAVEMAN_PROMPT                            3605 chars, frontmatter stripped, level ultra
live: claude -p "Explain database connection pooling."
      --append-system-prompt <prompt> --model haiku
      is_error False, $0.025
      -> "Pool reuses open DB connections. No new connection per request → skip
          handshake/auth overhead." + bold labels, arrows, fragments  = ultra style obeyed
points block   projects 9 bullets/2644 chars, obsidian 13/3913, zh-ai-support 19/3652
```

## Not live

Needs `sudo systemctl restart discord-claude` — waiting on Gaurav's yes per the BOT RESTART RULE.
