# Rex Voice: switched to natural female voice + conversational speaking style

**Date:** 2026-07-07 14:23
**Request:** Change the voice bot's TTS to a lady-like voice instead of male, and make it more natural in both voice and language.

## Changes

### 1. TTS voice: en_US-lessac-medium → en_US-hfc_female-medium
- Downloaded `en_US-hfc_female-medium.onnx` (+ `.json`) from HuggingFace `rhasspy/piper-voices` (v1.0.0) into `voice/models/` (~63 MB, 22.05 kHz).
- HFC female is generally considered the most natural-sounding English female Piper voice.
- `voice_bot.py`: `PIPER_MODEL` now reads env var `VOICE_TTS_VOICE` (filename inside `voice/models/`), defaulting to `en_US-hfc_female-medium.onnx`. Switching voices later = drop a model in `models/` and set one env var in the service file, no code edit.
- Old `en_US-lessac-medium.onnx` left in `models/` as fallback.

### 2. Speaking-style prompt made conversational
The per-utterance TTS instruction in `ask_claude()` now tells Claude to talk like a friendly person chatting — contractions, everyday words, short natural sentences, brief acknowledgements okay, don't spell out symbols/paths. Previously it just said "short, plain, conversational sentences".

## Verification
- Test synthesis of a sample sentence with the new model succeeded (`/tmp/voice_test.wav`).
- Service restarted 14:22, logged in clean: `logged in as Claudy Rex#5707 — whisper=base, model=haiku`. DAVE decrypt bridge still installed.

## Revert
Set `Environment=VOICE_TTS_VOICE=en_US-lessac-medium.onnx` in `/etc/systemd/system/discord-voice.service`, `sudo systemctl daemon-reload && sudo systemctl restart discord-voice`.

## Notes
- Alternative female voices if HFC doesn't land: `en_US-amy-medium`, `en_GB-jenny_dioco-medium` (British), `en_US-kristin-medium` — same HuggingFace repo path pattern.
- Voice quality ceiling is Piper itself; anything more natural (e.g. Kokoro TTS) would be a bigger change and heavier on the Pi.
