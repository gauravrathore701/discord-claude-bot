# Rex Voice — davey reinstalled + DAVE negotiation disabled via monkeypatch

**Date:** 2026-07-06 00:32
**Service:** `discord-voice.service` (restarted, PID 1923389)

## What broke after the 00:25 fix
Uninstalling `davey` made `!join` fail entirely:
`RuntimeError: davey library needed in order to use voice`
(discord/voice_client.py:222). discord.py 2.7.1 **hard-requires** davey to
construct any VoiceClient — removing it wasn't a viable fix.

## The actual fix (both constraints satisfied)
- `davey` **reinstalled** (0.1.6) so VoiceClient can be constructed.
- Monkeypatch in voice_bot.py before client creation:
  `discord.voice_state.VoiceConnectionState.max_dave_protocol_version = property(lambda self: 0)`
  This value is used in exactly one place (gateway.py:903, the voice IDENTIFY
  payload). Advertising 0 → Discord keeps the session at dave_protocol_version 0
  → transport-only encryption (aead_xchacha20_poly1305_rtpsize) → voice_recv can
  decrypt.
- Startup guard flipped: now exits FATAL if davey is *missing* (it's required),
  and logs "DAVE E2EE negotiation disabled" on boot.
- Verified offline: instantiating VoiceConnectionState with the patch reports
  advertised DAVE version 0.

## Memory note
`memory/rex_voice_dave_e2ee_incompatibility.md` (written at 00:25) says to keep
davey uninstalled — that is now WRONG; update it: davey must stay installed, the
monkeypatch is the protection. (Updated in same session.)

## Fragility note
The monkeypatch targets discord.py 2.7.1 internals (`VoiceConnectionState`).
On any discord.py upgrade, re-verify the property name and gateway usage.
