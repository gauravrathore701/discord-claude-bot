# Rex Voice — DAVE is MANDATORY; built receive-side E2EE decrypt bridge

**Date:** 2026-07-06 00:37
**Service:** `discord-voice.service` (restarted, PID 1951624)

## Why the 00:32 fix (advertise DAVE v0) caused a join/leave loop
Voice gateway rejected every handshake with **close code 4017** → discord.py
auto-retried forever → the join/leave flapping Gaurav saw. Web research:
**since 2026-03-01 Discord REQUIRES DAVE E2EE for all non-stage voice calls**
(support article "A/V E2EE Enforcement for Non-Stage Voice Calls"). Opting out
of DAVE is no longer possible. Reverted the max_dave_protocol_version=0 patch.

## The actual architecture problem
- discord.py 2.7.1 + davey: manages MLS group (proposals/commits/welcome in
  gateway.py), encrypts OUTGOING audio (`dave_session.encrypt_opus`). Never
  decrypts incoming — discord.py has no voice receive.
- discord-ext-voice-recv 0.5.2a179: no DAVE awareness at all; transport-decrypts
  then Opus-decodes the still-E2EE frame → OpusError → router thread dies.

## The bridge (voice_bot.py, replaces the v0 patch)
Monkeypatch `voice_recv.opus.PacketDecoder._decode_packet`:
- Resolve sender: `self._cached_id or vc._get_id_from_ssrc(self.ssrc)`.
- `packet.decrypted_data = state.dave_session.decrypt(user_id, davey.MediaType.audio, data)`
  (signature verified from davey's .pyi stub; `decrypted_data` is a writable slot).
- Skip fake/silence packets (falsy packet or ≤3 bytes).
- **Any failure → substitute OPUS_SILENCE** so the router thread can never die
  on a bad frame; failures logged throttled (every 50th).

## Verified
py_compile + import test show "bridge installed"; service restarted, logged in.
Awaiting live test (needs fresh !join).

## If decrypt fails at runtime
Watch for "[voice] DAVE decrypt failed" — possible causes: dave_session not ready
(MLS welcome not processed yet; transient at join), wrong MediaType enum use, or
davey API mismatch. Transient failures at session start are expected during the
passthrough transition window.
