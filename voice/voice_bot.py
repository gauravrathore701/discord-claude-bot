"""Rex Voice — Discord voice-call assistant.

Runs as a SEPARATE process from bot.py (same token, own gateway session) so the
text chat bot is never affected. Pipeline per utterance:

  voice packets (discord-ext-voice-recv, 48kHz s16le stereo)
    → VAD state machine (RMS threshold + trailing silence)
    → ffmpeg → 16kHz mono wav
    → faster-whisper (local STT)
    → claude CLI (same style as bot.py, own session per guild)
    → piper (local TTS)
    → played back into the voice channel

Commands (text, any channel the bot can read — use a channel NOT registered in
channels.json so bot.py doesn't also forward it to Claude):
  !join   — join your current voice channel and start listening
  !leave  — leave voice
  !voicestatus — pipeline status
"""

import asyncio
import audioop
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import discord
from discord.ext import voice_recv
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent          # .../discord-claude-bot/voice
load_dotenv(BASE_DIR.parent / ".env")

TOKEN = os.environ["DISCORD_TOKEN"]
ALLOWED_IDS = {int(u.strip()) for u in os.environ["DISCORD_ALLOWED_IDS"].split(",")}
VOICE_MODEL = os.environ.get("VOICE_MODEL")          # optional --model override
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/home/gaurav/.local/bin/claude")
WORK_DIR = os.environ.get("VOICE_WORK_DIR", "/home/gaurav/Projects")

PIPER_BIN = str(BASE_DIR / "venv" / "bin" / "piper")
PIPER_MODEL = str(BASE_DIR / "models" / "en_US-lessac-medium.onnx")
CHIME = {n: str(BASE_DIR / "models" / f"chime_{n}.wav") for n in ("ready", "thinking", "error")}
SESSIONS_DIR = BASE_DIR / ".claude-sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

WHISPER_MODEL_NAME = os.environ.get("VOICE_WHISPER_MODEL", "base")

# ── VAD tuning ────────────────────────────────────────────────────────────────
RMS_THRESHOLD = 400        # s16 RMS above this = voiced frame (20ms frames)
SILENCE_END_MS = 900       # this much trailing silence ends the utterance
MIN_UTTERANCE_MS = 500     # shorter than this = ignore (coughs, clicks)
MAX_UTTERANCE_MS = 30_000  # hard cap

CLAUDE_TIMEOUT = 180
SPOKEN_CHAR_LIMIT = 700    # longer replies get truncated in audio (full text still posted)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
client = discord.Client(intents=intents)

whisper_model = None       # loaded in background at startup


# ── claude CLI (mirrors bot.py's approach; own session file per guild) ───────
def _session_file(guild_id: int) -> Path:
    return SESSIONS_DIR / f"{guild_id}.json"


def _load_session(guild_id: int) -> str | None:
    try:
        return json.loads(_session_file(guild_id).read_text()).get("session_id")
    except Exception:
        return None


def _save_session(guild_id: int, session_id: str | None):
    if session_id:
        _session_file(guild_id).write_text(json.dumps({"session_id": session_id}))


def ask_claude(guild_id: int, text: str) -> str:
    prompt = (
        f"(Voice message from Gaurav, auto-transcribed — may contain small mis-hears)\n{text}\n\n"
        "IMPORTANT: your reply will be spoken aloud by TTS. Answer in short, plain,"
        " conversational sentences. No markdown, no code blocks, no lists, no emojis."
        " Keep it to a few sentences unless more detail is explicitly requested."
    )
    cmd = [CLAUDE_BIN, "--dangerously-skip-permissions", "--output-format", "json"]
    if VOICE_MODEL:
        cmd += ["--model", VOICE_MODEL]
    session_id = _load_session(guild_id)
    if session_id:
        cmd += ["--resume", session_id]
    cmd += ["-p", prompt]

    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT, cwd=WORK_DIR,
    )
    out = proc.stdout.strip()
    try:
        data = json.loads(out)
        _save_session(guild_id, data.get("session_id"))
        return (data.get("result") or "").strip() or "I came back with an empty answer, sorry."
    except json.JSONDecodeError:
        return out[:1000] if out else f"Claude CLI failed: {proc.stderr.strip()[:200]}"


# ── STT / TTS helpers (run in executor threads) ───────────────────────────────
def transcribe(pcm_48k_stereo: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as f:
        f.write(pcm_48k_stereo)
        raw = f.name
    wav = raw + ".wav"
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", "48000",
             "-ac", "2", "-i", raw, "-ar", "16000", "-ac", "1", wav],
            check=True, timeout=30,
        )
        segments, _ = whisper_model.transcribe(wav, language="en", beam_size=1)
        return " ".join(s.text for s in segments).strip()
    finally:
        for p in (raw, wav):
            try: os.unlink(p)
            except OSError: pass


_MD_CODEBLOCK = re.compile(r"```.*?```", re.DOTALL)
_MD_CHARS = re.compile(r"[*_#`>|~]")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_NON_SPEAKABLE = re.compile(r"[^\x20-\x7E\n]")


def to_speakable(text: str) -> str:
    text = _MD_CODEBLOCK.sub(" …code omitted, see text channel… ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_CHARS.sub("", text)
    text = _NON_SPEAKABLE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > SPOKEN_CHAR_LIMIT:
        text = text[:SPOKEN_CHAR_LIMIT].rsplit(" ", 1)[0] + " … more in the text channel."
    return text


def synthesize(text: str) -> str:
    wav = tempfile.mktemp(suffix=".wav")
    subprocess.run(
        [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", wav],
        input=text, text=True, check=True, timeout=120,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return wav


# ── per-guild voice session ───────────────────────────────────────────────────
class VoiceSession:
    def __init__(self, vc: voice_recv.VoiceRecvClient, text_channel: discord.abc.Messageable):
        self.vc = vc
        self.text_channel = text_channel
        self.busy = False            # True while STT→claude→TTS→playback runs
        self.buf = bytearray()
        self.voiced_ms = 0
        self.silence_ms = 0
        self.in_speech = False

    # runs on voice-recv's thread — keep it lean, no awaits
    def on_packet(self, user, data: voice_recv.VoiceData):
        if self.busy or user is None or user.id not in ALLOWED_IDS:
            return
        pcm = data.pcm
        if not pcm:
            return
        rms = audioop.rms(pcm, 2)
        frame_ms = len(pcm) / (48_000 * 2 * 2) * 1000  # bytes → ms (s16 stereo)

        if rms >= RMS_THRESHOLD:
            self.in_speech = True
            self.silence_ms = 0
            self.voiced_ms += frame_ms
            self.buf.extend(pcm)
        elif self.in_speech:
            self.silence_ms += frame_ms
            self.buf.extend(pcm)
            if self.silence_ms >= SILENCE_END_MS or (self.voiced_ms + self.silence_ms) >= MAX_UTTERANCE_MS:
                self._finalize()

    def _finalize(self):
        utterance = bytes(self.buf)
        voiced = self.voiced_ms
        self.buf.clear()
        self.voiced_ms = self.silence_ms = 0
        self.in_speech = False
        if voiced < MIN_UTTERANCE_MS:
            return
        self.busy = True
        asyncio.run_coroutine_threadsafe(self.handle_utterance(utterance), client.loop)

    async def play(self, wav_path: str):
        if not self.vc.is_connected():
            return
        self.vc.play(discord.FFmpegPCMAudio(wav_path))
        while self.vc.is_playing():
            await asyncio.sleep(0.2)

    async def handle_utterance(self, pcm: bytes):
        loop = asyncio.get_running_loop()
        try:
            text = await loop.run_in_executor(None, transcribe, pcm)
            if not text or len(text.split()) < 2:
                return  # noise / nothing intelligible — resume listening silently
            await self.text_channel.send(f"🎤 *heard:* “{text}”")
            await self.play(CHIME["thinking"])

            t0 = time.time()
            reply = await loop.run_in_executor(None, ask_claude, self.vc.guild.id, text)
            elapsed = int(time.time() - t0)

            for i in range(0, len(reply), 1900):
                await self.text_channel.send(reply[i:i + 1900] if i else f"🗣️ ({elapsed}s) {reply[:1900]}")
            spoken = to_speakable(reply)
            if spoken:
                wav = await loop.run_in_executor(None, synthesize, spoken)
                try:
                    await self.play(wav)
                finally:
                    try: os.unlink(wav)
                    except OSError: pass
        except Exception as e:
            print(f"[voice] pipeline error: {e!r}", flush=True)
            try:
                await self.text_channel.send(f"⚠️ voice pipeline error: `{e}`")
                await self.play(CHIME["error"])
            except Exception:
                pass
        finally:
            self.busy = False


sessions: dict[int, VoiceSession] = {}


@client.event
async def on_ready():
    print(f"[voice] logged in as {client.user} — whisper={WHISPER_MODEL_NAME}, model={VOICE_MODEL or 'default'}", flush=True)


@client.event
async def on_message(message: discord.Message):
    if message.author.bot or message.author.id not in ALLOWED_IDS:
        return
    cmd = message.content.strip().lower()

    if cmd == "!join":
        if not message.author.voice or not message.author.voice.channel:
            await message.reply("Join a voice channel first, then send `!join`.")
            return
        if whisper_model is None:
            await message.reply("Still loading the speech model — try again in a few seconds.")
            return
        old = sessions.pop(message.guild.id, None)
        if old and old.vc.is_connected():
            await old.vc.disconnect()
        vc = await message.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
        sess = VoiceSession(vc, message.channel)
        sessions[message.guild.id] = sess
        vc.listen(voice_recv.BasicSink(sess.on_packet))
        await message.reply(
            "🎙️ In the call and listening. Just talk — I detect when you stop. "
            "Expect a pause while I think (you'll hear “On it”). `!leave` when done."
        )
        await sess.play(CHIME["ready"])

    elif cmd == "!leave":
        sess = sessions.pop(message.guild.id, None)
        if sess and sess.vc.is_connected():
            await sess.vc.disconnect()
            await message.reply("Left the call. 👋")
        else:
            await message.reply("I'm not in a call.")

    elif cmd == "!voicestatus":
        sess = sessions.get(message.guild.id)
        await message.reply(
            f"whisper: `{WHISPER_MODEL_NAME}` {'✅ loaded' if whisper_model else '⏳ loading'}\n"
            f"in call: {'✅ ' + sess.vc.channel.name if sess and sess.vc.is_connected() else '❌'}\n"
            f"busy: {sess.busy if sess else '-'} | claude model: `{VOICE_MODEL or 'default'}`"
        )


async def _load_whisper():
    global whisper_model
    from faster_whisper import WhisperModel
    loop = asyncio.get_running_loop()
    whisper_model = await loop.run_in_executor(
        None, lambda: WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
    )
    print("[voice] whisper model loaded", flush=True)


async def main():
    async with client:
        asyncio.get_running_loop().create_task(_load_whisper())
        await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
