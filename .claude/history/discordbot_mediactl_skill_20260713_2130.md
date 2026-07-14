# mediactl global skill + YouTube ytInitialData fix

**Date:** 2026-07-13

## Changes

### 1. Fixed YouTube search (`mediactl.py`)
YouTube stopped hydrating `ytd-video-renderer` DOM elements (bot detection), so the old
CSS-selector approach returned `null` for every search. Fixed by reading `ytInitialData`
(a JS global YouTube always embeds in the page HTML) instead:

```js
// new primary path in JS_FIRST_RESULT
const items = ytInitialData.contents.twoColumnSearchResultsRenderer...
const vid = items.find(i => i.videoRenderer && i.videoRenderer.videoId);
return 'https://www.youtube.com/watch?v=' + vid.videoRenderer.videoId;
```

DOM-based selectors kept as fallback.

### 2. Created global skill (`~/.claude/skills/mediactl/SKILL.md`)
New Claude Code skill that documents the full `mediactl.py` interface. Auto-triggers on
any monitor/TV/YouTube/display request from any channel and any model. Contains:
- Command table (`video`, `play`, `stop`, `pause`, `resume`, `fullscreen`, `wake`, `sleep`, `status`)
- Intent → command mapping examples
- JSON output format
- Notes on ytInitialData fix and kiosk requirements

### 3. Slimmed down IMPORTANT POINTS in `bot.py`
The inline wall of mediactl docs in `run_claude()` replaced with a single short line that
references `/mediactl skill` for the full interface. Saves ~5 lines of context on every
request, especially beneficial for Haiku (smaller context window).

## Why
- YouTube search was completely broken (bot detection change on YouTube's side, ~2026-07)
- Inline docs were long and could crowd out context on smaller models (Haiku)
- Skill file is globally available to all future Claude invocations without touching bot.py again
