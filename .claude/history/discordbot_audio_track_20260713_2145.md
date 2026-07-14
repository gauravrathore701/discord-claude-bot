# YouTube audio track switching via CDP

**Date:** 2026-07-13

## Changes

### mediactl.py
- `JS_AUDIO_TRACKS` / `JS_CURRENT_AUDIO` — CDP JS snippets using YouTube's internal `#movie_player` API
- `_set_audio_track(track_id)` — calls `player.setAudioTrack(track)` via CDP
- `cmd_audio(arg)` — handles: `list`, `original`, language substring/code match, numeric index
- `main()` — wired `audio`, `track`, `lang`, `language` aliases

### ~/.claude/skills/mediactl/SKILL.md
- Added `audio` to command table
- Added "Audio track args" section with examples
- Added audio intent→command examples (hindi, original, english dub)

## How it works
YouTube's `#movie_player` element exposes `getAvailableAudioTracks()` and `setAudioTrack(track)`.
This works even when YouTube's DOM is not hydrated (bot detection mode) because the JS runs
in the page context after the player is loaded. Tested live: switched EvoFox video from
English (US) auto-dub to Hindi original successfully.
