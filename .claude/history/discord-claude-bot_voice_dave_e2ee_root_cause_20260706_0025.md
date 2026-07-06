# Rex Voice — ROOT CAUSE FOUND: DAVE E2EE via stray `davey` package

**Date:** 2026-07-06 00:25
**Service:** `discord-voice.service` (restarted, PID 1888830)

## The definitive trace (00:22 test, desktop, PTT, full sentence)
With logging finally enabled, the 00:22 `!join` showed:
1. Voice handshake: session description contained **`dave_protocol_version: 1`** —
   the session was end-to-end encrypted (Discord DAVE protocol).
2. Gaurav's speaking indicator fired (`speaking START: olddirtycarny`) — his client
   WAS transmitting fine. PTT/mic settings were never the problem.
3. First real voice packet → `discord.opus.OpusError: corrupted stream` in
   `voice_recv`'s PacketRouter thread → **thread dies** → zero packets forever after.
   Transport decryption succeeded but the payload was still DAVE-encrypted opus.

This also retroactively explains every earlier symptom: the 245ms "speech" at 00:11
(rms 16637) was decrypt garbage before the router died; second sessions got nothing
because the router was already dead or died instantly.

## Root cause
`davey 0.1.6` was installed in `voice/venv` (pulled in by `pip install discord.py[voice]`).
discord.py 2.7.1's `max_dave_protocol_version` advertises DAVE v1 when `davey` is
importable → Discord upgrades the session to E2EE → `discord-ext-voice-recv`
(0.5.2a179, zero DAVE support) cannot decrypt received frames.

## Fix
- `pip uninstall davey` in voice/venv → bot advertises DAVE v0 → Discord downgrades
  the session to transport-only encryption (`aead_xchacha20_poly1305_rtpsize`),
  which voice_recv fully supports.
- Added startup guard in voice_bot.py: if `davey` is importable, print FATAL with
  uninstall instructions and exit — protects against reinstall via discord.py[voice].

## Still pending
- Live confirmation from Gaurav (bot restarted, needs fresh `!join`).
- Once confirmed: dial `discord.ext.voice_recv` logger back from DEBUG to INFO.
- Consider `pip freeze` of voice/venv into voice/requirements.txt WITHOUT davey.
