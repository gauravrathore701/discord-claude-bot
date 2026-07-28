#!/usr/bin/env python3
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import discord
from dotenv import load_dotenv

from media import MediaPlayer

load_dotenv()

TOKEN        = os.environ["DISCORD_TOKEN"]
CHANNEL_ID   = int(os.environ["DISCORD_CHANNEL_ID"])
ALLOWED_IDS  = {int(uid.strip()) for uid in os.environ["DISCORD_ALLOWED_IDS"].split(",")}
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/home/gaurav/Projects")
CLAUDE_BIN   = os.environ.get("CLAUDE_BIN", "/home/gaurav/.local/bin/claude")
TIMEOUT      = int(os.environ.get("TASK_TIMEOUT", "1200"))  # seconds
PING_INTERVAL = 120  # seconds between "still working" edits

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
SESSIONS_ROOT   = os.path.join(BASE_DIR, ".claude", "sessions")
CHANNELS_FILE   = os.path.join(BASE_DIR, ".claude", "channels.json")
CHAT_HISTORY_MAX  = 5
RESET_HOUR      = 4
RESET_MINUTE    = 45

MODEL_ALIASES = {"sonnet", "opus", "haiku", "fable"}

DISCORD_LIMIT = 1900

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Single shared media player (one physical monitor/audio output on the Pi).
MEDIA = MediaPlayer(log=lambda m: print(m, flush=True))


# ── multi-channel config ─────────────────────────────────────────────────────

@dataclass
class ChannelConfig:
    id: int
    name: str
    root_dir: str | None        # None => use PROJECTS_DIR with project routing
    project_routing: bool
    notes: list[str]            # extra "important points" bullets for this channel
    omit: list[str] = field(default_factory=list)   # BASE_POINTS keys to drop here
    replace_points: bool = False  # True => use only `notes`, skip BASE_POINTS entirely


# Shared "important points" injected into every prompt. Keyed so a channel can
# drop individual ones via "omit" in channels.json.
BASE_POINTS: dict[str, str] = {
    "session":
        "This is a persistent daily session (resets at 04:45); retain and build on prior context from earlier in this session.",
    "recall":
        "CONTEXT RECALL: If the user refers to something you can't find or don't recognize (e.g., 'the prompt', 'that file', 'the error I sent'), "
        "FIRST search back through at least the last 5 exchanges of this session — what the user said and what you replied — "
        "before saying it doesn't exist or asking the user to repeat it.",
    "internet":
        "Search the internet if required to answer accurately or find up-to-date information.",
    "history":
        "Maintain a history folder inside the project's .claude folder; after any significant change, write a markdown file named as projectName_<short_description>_<YYYYMMDD_HHMM>.md documenting what was done.",
    "profile":
        "USER PROFILE: Read /home/gaurav/.claude/USER.md at the start of each session for context about the user. "
        "Whenever you learn something new about Gaurav (preferences, projects, tech choices, infrastructure details, working style), "
        "append it to /home/gaurav/.claude/USER.md under the '<!-- UPDATES -->' section with today's date. "
        "Keep entries concise — one or two lines per fact.",
    "personality":
        "PERSONALITY: Your name is Claudy Rex. Read /home/gaurav/.claude/CLAUDY_REX.md for your full identity and personality. "
        "Own that name — you are Claudy Rex, Gaurav's engineering AI on the Pi.",
    "restart":
        "BOT RESTART RULE: Before running `systemctl restart discord-claude`, ALWAYS: (1) summarize every change made, (2) explicitly ask Gaurav for confirmation. Never restart silently or as a side-effect. Wait for a clear yes before restarting.",
    "media":
        "MONITOR / YOUTUBE CONTROL (works from ANY channel, ANY model): for any request to play/show/stop/pause/resume "
        "something on the TV/screen/monitor, or to control the display (wake/sleep/fullscreen), invoke the /mediactl skill "
        "for the full interface, then RUN: `python3 /home/gaurav/Projects/discord-claude-bot/mediactl.py <cmd> [args]`. "
        "Interpret intent yourself — never tell Gaurav to type raw commands.",
}


def build_points_block(cfg: ChannelConfig) -> str:
    """Assemble the per-channel IMPORTANT POINTS block."""
    bullets: list[str] = []
    if not cfg.replace_points:
        bullets += [text for key, text in BASE_POINTS.items() if key not in cfg.omit]
    bullets += [n for n in cfg.notes if n.strip()]
    if not bullets:
        return ""
    body = "".join(f"- {b}\n" for b in bullets)
    return "\n\nIMPORTANT POINTS TO REMEMBER:\n" + body


@dataclass
class ChannelState:
    sessions_dir: str
    session_id: str | None = None
    session_start: float = 0.0
    session_last_used: float = 0.0
    prev_session_id: str | None = None
    prev_context_injected: bool = False
    model: str | None = None
    active_proc: asyncio.subprocess.Process | None = None
    active_task: asyncio.Task | None = None


def load_channels() -> dict[int, ChannelConfig]:
    """Load channel configs from .claude/channels.json. The entry with
    id "__DEFAULT__" is bound to DISCORD_CHANNEL_ID from .env so the original
    single-channel setup keeps working without editing the JSON file."""
    try:
        with open(CHANNELS_FILE) as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw = [{"id": "__DEFAULT__", "name": "projects", "root_dir": None,
                "project_routing": True, "notes": ""}]

    channels: dict[int, ChannelConfig] = {}
    for entry in raw:
        cid = CHANNEL_ID if entry["id"] == "__DEFAULT__" else int(entry["id"])
        notes = entry.get("notes", "")
        channels[cid] = ChannelConfig(
            id=cid,
            name=entry.get("name", str(cid)),
            root_dir=entry.get("root_dir"),
            project_routing=entry.get("project_routing", True),
            notes=list(notes) if isinstance(notes, list) else [notes],
            omit=entry.get("omit", []),
            replace_points=entry.get("replace_points", False),
        )
    return channels


CHANNELS = load_channels()
STATES: dict[int, ChannelState] = {
    cid: ChannelState(sessions_dir=os.path.join(SESSIONS_ROOT, str(cid)))
    for cid in CHANNELS
}


def channel_paths(state: ChannelState) -> dict[str, str]:
    d = state.sessions_dir
    return {
        "session": os.path.join(d, "current.json"),
        "model": os.path.join(d, "model.json"),
        "history": os.path.join(d, "chat_history.json"),
        "summary": os.path.join(d, "prev_summary.json"),
    }


def get_cycle_start() -> float:
    """Timestamp of the most recent 4:45 AM daily reset."""
    now = datetime.now()
    cutoff = now.replace(hour=RESET_HOUR, minute=RESET_MINUTE, second=0, microsecond=0)
    if now < cutoff:
        cutoff -= timedelta(days=1)
    return cutoff.timestamp()


def next_reset_dt() -> datetime:
    now = datetime.now()
    cutoff = now.replace(hour=RESET_HOUR, minute=RESET_MINUTE, second=0, microsecond=0)
    if now >= cutoff:
        cutoff += timedelta(days=1)
    return cutoff


def session_active(state: ChannelState) -> bool:
    return bool(state.session_id) and state.session_start >= get_cycle_start()


def session_age_str(state: ChannelState) -> str:
    if not state.session_id:
        return "no session"
    elapsed = int(time.time() - state.session_start)
    h, m = divmod(elapsed, 3600)
    ttl_left = int((next_reset_dt() - datetime.now()).total_seconds())
    th, tm = divmod(max(0, ttl_left), 3600)
    return (
        f"ID: `{state.session_id[:8]}…`\n"
        f"Age: {h}h {m % 60}m\n"
        f"Resets in: {th}h {tm % 60}m (daily at 04:45)"
    )


def load_session(state: ChannelState):
    try:
        with open(channel_paths(state)["session"]) as f:
            data = json.load(f)
        state.session_id = data.get("session_id")
        state.session_start = float(data.get("session_start", 0.0))
        state.session_last_used = float(data.get("session_last_used", 0.0))
        state.prev_session_id = data.get("prev_session_id")
        if not session_active(state):
            # current session expired — promote it to prev for context bridging
            if state.session_id:
                state.prev_session_id = state.session_id
            state.session_id = None
            state.session_start = 0.0
            state.session_last_used = 0.0
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def save_session(state: ChannelState):
    os.makedirs(state.sessions_dir, exist_ok=True)
    with open(channel_paths(state)["session"], "w") as f:
        json.dump({
            "session_id": state.session_id,
            "session_start": state.session_start,
            "session_last_used": state.session_last_used,
            "prev_session_id": state.prev_session_id,
        }, f, indent=2)


def load_summary(state: ChannelState) -> str:
    try:
        with open(channel_paths(state)["summary"]) as f:
            return json.load(f).get("summary", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return ""


def save_summary(state: ChannelState, summary: str):
    os.makedirs(state.sessions_dir, exist_ok=True)
    with open(channel_paths(state)["summary"], "w") as f:
        json.dump({"summary": summary, "generated_at": datetime.now().isoformat()}, f, indent=2)


def load_model(state: ChannelState):
    try:
        with open(channel_paths(state)["model"]) as f:
            state.model = json.load(f).get("model")
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def save_model(state: ChannelState):
    os.makedirs(state.sessions_dir, exist_ok=True)
    with open(channel_paths(state)["model"], "w") as f:
        json.dump({"model": state.model}, f, indent=2)


def load_chat_history(state: ChannelState) -> list[dict]:
    try:
        with open(channel_paths(state)["history"]) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data[-CHAT_HISTORY_MAX:]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def append_chat_history(state: ChannelState, query: str, response: str):
    history = load_chat_history(state)
    history.append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "q": query[:2000],
        "r": response[:3000],
    })
    history = history[-CHAT_HISTORY_MAX:]
    os.makedirs(state.sessions_dir, exist_ok=True)
    with open(channel_paths(state)["history"], "w") as f:
        json.dump(history, f, indent=2)


def format_chat_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = ["[Recent chat history — last 5 exchanges]"]
    for i, entry in enumerate(history, 1):
        lines.append(f"\n--- Exchange {i} ({entry.get('ts', '?')}) ---")
        lines.append(f"User: {entry['q']}")
        lines.append(f"You: {entry['r']}")
    return "\n".join(lines)


async def fetch_prev_summary(session_id: str) -> str:
    """Fetch a bullet-point summary of a previous session for context bridging."""
    prompt = (
        "Summarize this session in 5 bullet points max. Include: what tasks were done, "
        "key decisions made, any problems encountered and how they were resolved. "
        "Be terse — one line per bullet. No preamble."
    )
    cmd = [CLAUDE_BIN, "--dangerously-skip-permissions", "--output-format", "json",
           "--resume", session_id, "-p", prompt]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "TERM": "dumb"},
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        data = json.loads(stdout.decode(errors="replace").strip())
        return data.get("result", "").strip()
    except Exception:
        return ""


async def do_daily_rollover(state: ChannelState) -> bool:
    """Summarize the expiring session and rotate it to prev_session_id, ahead of the
    next message — so the new day's first reply already has yesterday's context baked in."""
    if state.active_task and not state.active_task.done():
        return False  # don't summarize/rotate mid-task; caller retries shortly

    expiring_id = state.session_id
    if expiring_id:
        summary = await fetch_prev_summary(expiring_id)
        if summary:
            save_summary(state, summary)
        state.prev_session_id = expiring_id

    state.session_id = None
    state.session_start = 0.0
    state.session_last_used = 0.0
    state.prev_context_injected = False
    save_session(state)
    print(f"[rollover] Session {str(expiring_id)[:8] if expiring_id else '(none)'} summarized and rotated.", flush=True)
    return True


async def daily_rollover_loop():
    """Background task: fire do_daily_rollover() for every configured channel once
    per day at RESET_HOUR:RESET_MINUTE. If a channel's task is mid-flight at the
    target time, retry that channel every 30s until it succeeds."""
    while True:
        target = next_reset_dt()
        wait_s = max(1.0, (target - datetime.now()).total_seconds())
        await asyncio.sleep(wait_s)
        pending = set(STATES.keys())
        while pending:
            for cid in list(pending):
                try:
                    done = await do_daily_rollover(STATES[cid])
                except Exception as e:
                    print(f"[rollover] channel {cid} failed: {e}", flush=True)
                    done = True  # avoid a tight retry loop on persistent errors
                if done:
                    pending.discard(cid)
            if pending:
                await asyncio.sleep(30)


# ── helpers ──────────────────────────────────────────────────────────────────

def resolve_dir(cfg: ChannelConfig, content: str) -> tuple[str, str]:
    """
    For channels with project_routing enabled and a message starting with
    'projectname: task', resolve the project subdirectory under PROJECTS_DIR.
    Otherwise run in the channel's fixed root_dir (or PROJECTS_DIR).
    Returns (working_dir, task_text).
    """
    base_dir = cfg.root_dir or PROJECTS_DIR
    if cfg.project_routing:
        m = re.match(r'^([\w][\w\-_.]*)\s*:\s*(.+)$', content, re.DOTALL)
        if m:
            name, task = m.group(1), m.group(2).strip()
            candidate = os.path.join(base_dir, name)
            if os.path.isdir(candidate):
                return candidate, task
    return base_dir, content


async def run_claude(cfg: ChannelConfig, state: ChannelState, task: str, cwd: str) -> str:
    # Bridge previous day context into the first message of a new session.
    # Normally daily_rollover_loop() already generated this at 04:45; fall back to a
    # lazy fetch here only if the bot was offline at rollover time and it never ran.
    prev_context_block = ""
    if not session_active(state) and state.prev_session_id and not state.prev_context_injected:
        summary = load_summary(state)
        if not summary:
            summary = await fetch_prev_summary(state.prev_session_id)
        if summary:
            prev_context_block = (
                f"[Previous day's session summary — for context]\n{summary}\n\n---\n\n"
            )
        state.prev_context_injected = True

    # Inject rolling chat history for context continuity
    history = load_chat_history(state)
    history_block = ""
    if history:
        history_block = format_chat_history(history) + "\n\n---\n\n"

    task_with_ctx = (
        prev_context_block +
        history_block +
        task +
        build_points_block(cfg)
    )

    cmd = [CLAUDE_BIN, "--dangerously-skip-permissions", "--output-format", "json"]
    if state.model:
        cmd += ["--model", state.model]
    if session_active(state):
        cmd += ["--resume", state.session_id]
    cmd += ["-p", task_with_ctx]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env={**os.environ, "TERM": "dumb"},
    )
    state.active_proc = proc
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return f"Timed out after {TIMEOUT}s."
    finally:
        state.active_proc = None

    raw = stdout.decode(errors="replace").strip()
    err = stderr.decode(errors="replace").strip()

    out = raw
    try:
        data = json.loads(raw)
        out = data.get("result", raw)
        if data.get("is_error"):
            out = f"[error] {out}"
        new_sid = data.get("session_id")
        if new_sid:
            now = time.time()
            if not state.session_id:
                state.session_start = now
            state.session_id = new_sid
            state.session_last_used = now
            save_session(state)
    except (json.JSONDecodeError, AttributeError):
        pass

    if err:
        out += f"\n\n[stderr]\n{err}"

    final_out = out or "(no output)"
    append_chat_history(state, task, final_out)
    return final_out


async def progress_ping(status_msg: discord.Message, cwd: str):
    """Edit the status message every PING_INTERVAL seconds to show elapsed time."""
    start = time.time()
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            elapsed = int(time.time() - start)
            m, s = divmod(elapsed, 60)
            await status_msg.edit(content=f"Working in `{cwd}`... ({m}m{s:02d}s elapsed)")
    except (asyncio.CancelledError, discord.NotFound, discord.HTTPException):
        pass


async def send_long(channel, text: str, reply_to=None):
    """Send text, splitting into multiple messages if it exceeds Discord's limit."""
    chunk_size = DISCORD_LIMIT - 8  # leave room for the ```\n ... \n``` fence
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]

    for i, chunk in enumerate(chunks):
        body = f"```\n{chunk}\n```"
        if reply_to and i == 0:
            await reply_to.reply(body)
        else:
            await channel.send(body)


def list_projects() -> str:
    try:
        entries = sorted(
            e for e in os.listdir(PROJECTS_DIR)
            if os.path.isdir(os.path.join(PROJECTS_DIR, e)) and not e.startswith('.')
        )
        return "\n".join(entries) if entries else "(none)"
    except OSError as e:
        return str(e)


# ── bot events ────────────────────────────────────────────────────────────────

_rollover_task: asyncio.Task | None = None


@client.event
async def on_ready():
    global _rollover_task
    for state in STATES.values():
        load_session(state)
        load_model(state)
    print(f"Online as {client.user}", flush=True)
    print(f"Configured channels: {[(cid, cfg.name) for cid, cfg in CHANNELS.items()]}", flush=True)
    if _rollover_task is None or _rollover_task.done():
        _rollover_task = asyncio.create_task(daily_rollover_loop())
    # NOTE: monitor is now manual/desktop-owned. Bot no longer auto-launches the
    # cage clock kiosk on boot (it raced lightdm for DRM -> black screen). The
    # physical monitor stays on via LXDE + ~/.config/autostart/monitor-always-on.desktop.
    # asyncio.create_task(MEDIA.startup())   # DISABLED — no boot-time display grab
    for cid, cfg in CHANNELS.items():
        ch = client.get_channel(cid)
        if ch:
            await ch.send(f"Claude Code bot is online ({cfg.name}). Send a task or type `!help`.")


@client.event
async def on_message(message: discord.Message):
    cfg = CHANNELS.get(message.channel.id)
    if cfg is None:
        return
    state = STATES[cfg.id]

    if message.author.bot:
        return
    if message.author.id not in ALLOWED_IDS:
        await message.reply("Unauthorized.")
        return

    text = message.content.strip()
    image_attachments = [
        a for a in message.attachments
        if a.content_type and a.content_type.startswith("image/")
    ]
    file_attachments = [
        a for a in message.attachments
        if a not in image_attachments
    ]

    if not text and not image_attachments and not file_attachments:
        return

    # ── built-in commands ────────────────────────────────────────────────────
    if text.lower() == "!help":
        project_help = (
            "To target a specific project: `projectname: your task here`\n\n"
            if cfg.project_routing else
            f"This channel always runs in `{cfg.root_dir}`.\n\n"
        )
        await message.reply(
            f"**Commands** (channel: `{cfg.name}`)\n"
            "`!help` — show this\n"
            "`!projects` — list projects in PROJECTS_DIR\n"
            "`!points` — show this channel's IMPORTANT POINTS block\n"
            "`!cancel` — kill the running task\n"
            "`!status` — check if a task is running\n"
            "`!session` — show current session info\n"
            "`!newsession` — start a fresh Claude session\n"
            "`model <sonnet|opus|haiku|fable|default>` — switch model (also `!model`, no arg shows current)\n\n"
            "**Media / monitor** (YouTube in a browser on the Pi's HDMI monitor)\n"
            "`!play <song or url>` — play (audio focus, doesn't wake the screen)\n"
            "`!video <query or url>` — play and wake the monitor\n"
            "`!pause` / `!resume` — pause / resume playback\n"
            "`!mstop` — stop playback\n"
            "`!np` — now playing / display status\n"
            "`!wake` / `!sleep` — turn the HDMI output on / off\n"
            "_(browser closes + screen blanks after 30 min idle; play/wake restores)_\n\n"
            "**Running a task**\n"
            f"Just type your task. {project_help}"
            "**Sessions**\n"
            "Claude remembers context within each day, per channel. "
            "Sessions reset automatically at 04:45 every morning, or use `!newsession`."
        )
        return

    if text.lower() == "!projects":
        await message.reply(f"```\n{list_projects()}\n```")
        return

    if text.lower() == "!points":
        block = build_points_block(cfg) or "(none — no base points, no notes)"
        await send_long(message.channel, f"[channel: {cfg.name}]{block}", reply_to=message)
        return

    if text.lower() == "!session":
        status_line = "Active" if session_active(state) else "Expired / none"
        await message.reply(f"**Session status:** {status_line}\n{session_age_str(state)}")
        return

    if text.lower() == "!newsession":
        if state.session_id:
            state.prev_session_id = state.session_id
        state.session_id = None
        state.session_start = 0.0
        state.session_last_used = 0.0
        state.prev_context_injected = False
        save_session(state)
        await message.reply("Session cleared. Next message starts a fresh conversation.")
        return

    m = re.match(r'^!?model(?:\s+(\S+))?$', text, re.IGNORECASE)
    if m:
        arg = m.group(1)
        if not arg:
            current = state.model or "default"
            await message.reply(
                f"Current model: `{current}`\n"
                f"Usage: `model <{'|'.join(sorted(MODEL_ALIASES))}|default>`"
            )
            return
        choice = arg.lower()
        if choice == "default":
            state.model = None
        elif choice in MODEL_ALIASES:
            state.model = choice
        else:
            await message.reply(
                f"Unknown model `{arg}`. Valid: {', '.join(sorted(MODEL_ALIASES))}, default"
            )
            return
        save_model(state)
        await message.reply(f"Model set to `{state.model or 'default'}`. Applies to the next message.")
        return

    if text.lower() in ("!cancel", "!stop"):
        if state.active_proc:
            state.active_proc.kill()
        if state.active_task and not state.active_task.done():
            state.active_task.cancel()
            await message.reply("Cancelled.")
        else:
            await message.reply("Nothing is running.")
        return

    if text.lower() == "!status":
        running = state.active_task and not state.active_task.done()
        await message.reply("A task is running." if running else "Idle.")
        return

    # ── media / display commands (shared single monitor, run independently) ───
    low = text.lower()
    m_play = re.match(r'^!(play|video|playvideo)\s+(.+)$', text, re.IGNORECASE | re.DOTALL)
    if m_play:
        video = m_play.group(1).lower() in ("video", "playvideo")
        query = m_play.group(2).strip()
        async with message.channel.typing():
            ok, info = await MEDIA.play(query, video=video)
        if ok:
            await message.reply(f"{'📺' if video else '🎵'} Now playing: **{info}**")
        else:
            await message.reply(f"⚠️ {info}")
        return

    if low in ("!mstop", "!stopmusic", "!mediastop"):
        was = await MEDIA.stop()
        await message.reply("⏹ Stopped." if was else "Nothing was playing.")
        return

    if low == "!pause":
        ok = await MEDIA.pause()
        await message.reply("⏸ Paused." if ok else "Nothing to pause.")
        return

    if low == "!resume":
        ok = await MEDIA.resume()
        await message.reply("▶ Resumed." if ok else "Nothing to resume.")
        return

    if low in ("!wake", "!screenon"):
        ok, msg = await MEDIA.display(True)
        await message.reply(f"🖥️ {msg}" if ok else f"⚠️ {msg}")
        return

    if low in ("!sleep", "!screenoff"):
        ok, msg = await MEDIA.display(False)
        await message.reply(f"🌙 {msg}" if ok else f"⚠️ {msg}")
        return

    if low in ("!np", "!nowplaying", "!mstatus"):
        await message.reply(await MEDIA.status())
        return

    # ── reject concurrent tasks (per channel) ────────────────────────────────
    if state.active_task and not state.active_task.done():
        await message.reply("Already running a task in this channel. Use `!cancel` to stop it first.")
        return

    # ── download image attachments to temp files ─────────────────────────────
    image_paths = []
    for attachment in image_attachments:
        ext = attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else "png"
        if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
            ext = "png"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}", prefix="discord_img_")
        tmp.close()
        await attachment.save(tmp.name)
        image_paths.append(tmp.name)

    # ── download file attachments to temp files ───────────────────────────────
    file_paths = []
    for attachment in file_attachments:
        fname = attachment.filename
        suffix = f"_{fname}" if fname else ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="discord_file_")
        tmp.close()
        await attachment.save(tmp.name)
        file_paths.append((fname, tmp.name))

    # ── dispatch task ────────────────────────────────────────────────────────
    cwd, task = resolve_dir(cfg, text)

    if image_paths:
        img_note = "\n".join(
            f"[Image attached — read this file with your Read tool: {p}]"
            for p in image_paths
        )
        task = f"{task}\n\n{img_note}" if task else f"The user sent an image. Read it and respond:\n{img_note}"

    if file_paths:
        file_note = "\n".join(
            f"[File attached: '{name}' — read it with your Read tool at path: {path}]"
            for name, path in file_paths
        )
        task = f"{task}\n\n{file_note}" if task else f"The user sent a file. Read it and respond:\n{file_note}"

    status = await message.reply(f"Working in `{cwd}`...")

    async def do_task():
        ping = asyncio.create_task(progress_ping(status, cwd))
        try:
            async with message.channel.typing():
                output = await run_claude(cfg, state, task, cwd)
            ping.cancel()
            try:
                await status.delete()
            except discord.NotFound:
                pass
            await send_long(message.channel, output, reply_to=message)
        except asyncio.CancelledError:
            ping.cancel()
            try:
                await status.delete()
            except discord.NotFound:
                pass
            await message.reply("Task was cancelled.")
        finally:
            for p in image_paths:
                try:
                    os.unlink(p)
                except OSError:
                    pass
            for _, p in file_paths:
                try:
                    os.unlink(p)
                except OSError:
                    pass

    state.active_task = asyncio.create_task(do_task())


if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID or not ALLOWED_IDS:
        print("ERROR: DISCORD_TOKEN, DISCORD_CHANNEL_ID, DISCORD_OWNER_ID must be set in .env")
        sys.exit(1)
    client.run(TOKEN)
