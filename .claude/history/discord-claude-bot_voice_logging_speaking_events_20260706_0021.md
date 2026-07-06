# Rex Voice — zero packets received; added logging + speaking events to split diagnosis

**Date:** 2026-07-06 00:21
**File:** `voice/voice_bot.py` | **Service:** `discord-voice.service` (restarted, PID 1865723)

## State of the bug hunt
- 00:11 test: packets arrived (rms_peak 16637) but only 245ms total, then stream died.
- 00:17 test (after PTT advice + reconnect fix): bot joined 'General', **zero packets ever** —
  `on_packet` never called once. Playback (greeting) works; receive path fully dead.
- Matches upstream [discord-ext-voice-recv issue #27] "bot suddenly stops listening"
  (closed without documented fix). We're on the latest release (0.5.2a179,
  discord.py 2.7.1, PyNaCl 1.5.0).

## Blind spot fixed
`client.start()` (unlike `client.run()`) configures no logging — every warning from
discord.py / voice_recv (decrypt failures, dead reader thread, SSRC issues) was
being swallowed. Now: `logging.basicConfig(INFO)` to stderr→journald, with
`discord.ext.voice_recv` at DEBUG.

## New diagnosis instrumentation
- `RexSink(BasicSink)` with `on_voice_member_speaking_start/stop` sink listeners.
- Client-level `on_voice_member_speaking_state(*args)` event logger.

**Decision table for next test:**
- speaking START logged + no packet reports → receive/decrypt broken bot-side
  (likely voice_recv bug / Discord protocol change; consider git-main install or Pycord).
- no speaking events at all → Gaurav's client isn't transmitting (mic settings,
  PTT not held / mobile client).

## Open question for Gaurav
Desktop or phone? (Mobile Discord defaults to voice activity; PTT behaves differently.)
