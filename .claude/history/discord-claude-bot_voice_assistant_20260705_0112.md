# Rex Voice — Discord voice-call assistant (separate service)

**Date:** 2026-07-05 01:12

## What was built
Full voice loop: speak in a Discord voice call → Whisper (local STT) → Claude CLI
→ Piper (local TTS) → Rex speaks the answer back in the call. 100% free & on-device.

## Architecture (chose isolation over integration)
- **Separate process** `voice/voice_bot.py`, own venv (`voice/venv`), own systemd
  unit `discord-voice.service`, SAME bot token (second gateway session — allowed).
  `bot.py` / `discord-claude.service` were not modified at all — zero risk to text chat.
- Separate venv is mandatory anyway: voice needs `discord-ext-voice-recv` (0.5.2a)
  which shares the `discord` package namespace.

## Pipeline detail
- **Receive**: `voice_recv.VoiceRecvClient` + `BasicSink` → 48kHz s16 stereo PCM
  20ms frames, only from `DISCORD_ALLOWED_IDS` users.
- **VAD**: RMS ≥ 400 = voiced; utterance ends after 900ms silence; < 500ms voiced
  ignored; 30s cap. Callback runs on voice-recv's thread → hops to event loop via
  `run_coroutine_threadsafe`. `busy` flag = ignore audio while processing (no barge-in).
- **STT**: faster-whisper `base` int8 CPU (~1x realtime on Pi 5; `small` was 2.6x —
  too slow). ffmpeg converts 48k stereo raw → 16k mono wav first. Model preloads at
  startup (~2s). Override via `VOICE_WHISPER_MODEL`.
- **Claude**: same CLI invocation style as bot.py (`--output-format json`,
  `--dangerously-skip-permissions`), cwd=/home/gaurav/Projects, per-guild session
  resume in `voice/.claude-sessions/<guild>.json`. Optional `VOICE_MODEL` env.
  Prompt wrapper demands short plain spoken-style answers (no markdown).
- **TTS**: Piper `en_US-lessac-medium` (63MB onnx in `voice/models/`), ~4s for a
  sentence-pair. Markdown stripped, >700 chars truncated in audio (full reply still
  posted as text). Pre-generated chimes: ready / "On it." / error.
- Transcript (`🎤 heard: …`) and full reply are also posted to the text channel
  where `!join` was sent — catches mis-hears.

## Commands (allowed users only)
`!join` (join the user's current VC and listen), `!leave`, `!voicestatus`.
**Use a text channel NOT in channels.json** — bot.py forwards any text in its
registered channels to Claude, so `!join` there would trigger both bots.

## Verified
- Piper→Whisper loopback transcribed near-perfectly.
- Service starts, whisper loads (2s), gateway login OK as second session;
  `discord-claude.service` unaffected (both active).
- NOT yet live-tested in an actual call (needs a human speaking) — Gaurav to test.

## Known limits
- Answer latency = whisper (~1x audio len) + claude CLI (10–60s+) + piper (~4s).
  It's a voice assistant, not a conversation partner.
- No barge-in; talking while Rex thinks/speaks is ignored.
- VAD threshold (RMS 400) may need tuning to mic/noise — constant at top of file.
