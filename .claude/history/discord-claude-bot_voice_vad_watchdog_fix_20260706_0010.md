# Rex Voice — VAD never finalized utterances (watchdog fix)

**Date:** 2026-07-06 00:10
**File:** `voice/voice_bot.py` | **Service:** `discord-voice.service` (restarted, PID 1807119)

## Symptom
Gaurav joined a call, Rex connected and played the greeting, but never reacted to
speech — no `🎤 heard:` message, no "On it" chime, no reply.

## Root cause
Turn detection was purely packet-driven: it finalized an utterance after
`SILENCE_END_MS` (900ms) worth of *quiet packets*. But Discord stops transmitting
voice packets a few frames after the speaker goes quiet, so those quiet packets
never arrive. `in_speech` stayed True with the audio stuck in the buffer forever —
the pipeline never fired.

## Fix
- `silence_watchdog()` task per session (started on `!join`, cancelled on `!leave`
  / re-join): every 200ms, if `in_speech` and no voiced packet for `SILENCE_END_MS`
  (wall clock via `last_voiced_t`), finalize the utterance.
- `threading.Lock` around VAD state — `on_packet` runs on the voice-recv thread,
  the watchdog on the event loop.
- Max-utterance cap now also checked on voiced frames (previously only on quiet ones).
- Diagnostics: 5-second packet/RMS-peak reports, utterance captured/too-short lines,
  transcription results, join confirmation, one-shot warning for unresolved or
  disallowed speakers.
- `RMS_THRESHOLD` now overridable via `VOICE_RMS_THRESHOLD` env var (default 400) —
  tune in the systemd unit / .env without code edits.

## Verification
`py_compile` clean; service restarted, whisper loaded, gateway login OK
(`Claudy Rex#5707`). Live mic test pending — logs now show rms_peak every 5s while
packets flow, so if speech is still missed, compare rms_peak against threshold.
