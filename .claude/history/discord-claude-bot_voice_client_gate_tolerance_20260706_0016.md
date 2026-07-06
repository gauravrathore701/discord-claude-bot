# Rex Voice — client-side mic gating diagnosed; bot made tolerant

**Date:** 2026-07-06 00:16
**File:** `voice/voice_bot.py` | **Service:** `discord-voice.service` (restarted, PID 1839858)

## Diagnosis (from the new packet/RMS logs, 00:11 test)
- Mic level is strong: rms_peak **16637** vs threshold 400 → threshold was never the problem.
- Watchdog fix from 00:10 works — it finalized an utterance.
- BUT only **245ms** of audio ever arrived from Discord, then packets stopped;
  after a re-`!join`, **zero** packets. Conclusion: Gaurav's Discord client
  (Voice Activity gate / noise suppression) is transmitting almost nothing.
  The 245ms fragment was then silently dropped by MIN_UTTERANCE_MS with no user feedback.

## Recommendation given to Gaurav
Switch Discord Input Mode to **Push to Talk** (User Settings → Voice & Video) or set
Input Sensitivity to manual/low. PTT needs no bot changes — the wall-clock watchdog
finalizes 0.9s after key release.

## Bot-side changes
- `RMS_THRESHOLD` default 400 → **250**; `MIN_UTTERANCE_MS` 500 → **350** (client
  gate clips utterance edges).
- **Pre-roll buffer**: last ~400ms of sub-threshold audio prepended when speech
  starts, so soft first syllables aren't lost.
- **Visible feedback on too-short discards**: posts to the text channel (throttled
  to 1/10s) telling the user how much was caught and pointing at PTT settings —
  no more silent failures.
- `!join` while already connected now sleeps 1s between disconnect and reconnect
  (suspected dirty voice-recv reconnect caused the zero-packet second session).

## Verification
py_compile clean, service restarted, whisper loaded, logged in as Claudy Rex#5707.
Awaiting live PTT test.
