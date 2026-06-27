#!/usr/bin/env python3
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN        = os.environ["DISCORD_TOKEN"]
CHANNEL_ID   = int(os.environ["DISCORD_CHANNEL_ID"])
ALLOWED_IDS  = {int(uid.strip()) for uid in os.environ["DISCORD_ALLOWED_IDS"].split(",")}
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/home/gaurav/Projects")
CLAUDE_BIN   = os.environ.get("CLAUDE_BIN", "/home/gaurav/.local/bin/claude")
TIMEOUT      = int(os.environ.get("TASK_TIMEOUT", "1200"))  # seconds
PING_INTERVAL = 120  # seconds between "still working" edits

SESSIONS_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".claude", "sessions")
SESSION_FILE    = os.path.join(SESSIONS_DIR, "current.json")
MODEL_FILE      = os.path.join(SESSIONS_DIR, "model.json")
CHAT_HISTORY_FILE = os.path.join(SESSIONS_DIR, "chat_history.json")
SUMMARY_FILE    = os.path.join(SESSIONS_DIR, "prev_summary.json")
CHAT_HISTORY_MAX  = 5
RESET_HOUR      = 4
RESET_MINUTE    = 45

MODEL_ALIASES = {"sonnet", "opus", "haiku", "fable"}

DISCORD_LIMIT = 1900

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

active_proc: asyncio.subprocess.Process | None = None
active_task: asyncio.Task | None = None

# Session state
_session_id: str | None = None
_session_start: float = 0.0
_session_last_used: float = 0.0
_prev_session_id: str | None = None   # previous day's session for context bridging
_prev_context_injected: bool = False  # inject prev context only once per new session

# Model override (None = use the default from ~/.claude/settings.json)
_model: str | None = None


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


def session_active() -> bool:
    return bool(_session_id) and _session_start >= get_cycle_start()


def session_age_str() -> str:
    if not _session_id:
        return "no session"
    elapsed = int(time.time() - _session_start)
    h, m = divmod(elapsed, 3600)
    ttl_left = int((next_reset_dt() - datetime.now()).total_seconds())
    th, tm = divmod(max(0, ttl_left), 3600)
    return (
        f"ID: `{_session_id[:8]}…`\n"
        f"Age: {h}h {m % 60}m\n"
        f"Resets in: {th}h {tm % 60}m (daily at 04:45)"
    )


def load_session():
    global _session_id, _session_start, _session_last_used, _prev_session_id
    try:
        with open(SESSION_FILE) as f:
            data = json.load(f)
        _session_id = data.get("session_id")
        _session_start = float(data.get("session_start", 0.0))
        _session_last_used = float(data.get("session_last_used", 0.0))
        _prev_session_id = data.get("prev_session_id")
        if not session_active():
            # current session expired — promote it to prev for context bridging
            if _session_id:
                _prev_session_id = _session_id
            _session_id = None
            _session_start = 0.0
            _session_last_used = 0.0
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def save_session():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        json.dump({
            "session_id": _session_id,
            "session_start": _session_start,
            "session_last_used": _session_last_used,
            "prev_session_id": _prev_session_id,
        }, f, indent=2)


def load_summary() -> str:
    try:
        with open(SUMMARY_FILE) as f:
            return json.load(f).get("summary", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return ""


def save_summary(summary: str):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(SUMMARY_FILE, "w") as f:
        json.dump({"summary": summary, "generated_at": datetime.now().isoformat()}, f, indent=2)


def load_model():
    global _model
    try:
        with open(MODEL_FILE) as f:
            _model = json.load(f).get("model")
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def save_model():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(MODEL_FILE, "w") as f:
        json.dump({"model": _model}, f, indent=2)


def load_chat_history() -> list[dict]:
    try:
        with open(CHAT_HISTORY_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data[-CHAT_HISTORY_MAX:]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def append_chat_history(query: str, response: str):
    history = load_chat_history()
    history.append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "q": query[:2000],
        "r": response[:3000],
    })
    history = history[-CHAT_HISTORY_MAX:]
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(CHAT_HISTORY_FILE, "w") as f:
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


async def do_daily_rollover():
    """Summarize the expiring session and rotate it to prev_session_id, ahead of the
    next message — so the new day's first reply already has yesterday's context baked in."""
    global _session_id, _session_start, _session_last_used, _prev_session_id, _prev_context_injected

    if active_task and not active_task.done():
        return False  # don't summarize/rotate mid-task; caller retries shortly

    expiring_id = _session_id
    if expiring_id:
        summary = await fetch_prev_summary(expiring_id)
        if summary:
            save_summary(summary)
        _prev_session_id = expiring_id

    _session_id = None
    _session_start = 0.0
    _session_last_used = 0.0
    _prev_context_injected = False
    save_session()
    print(f"[rollover] Session {str(expiring_id)[:8] if expiring_id else '(none)'} summarized and rotated.", flush=True)
    return True


async def daily_rollover_loop():
    """Background task: fire do_daily_rollover() once per day at RESET_HOUR:RESET_MINUTE.
    If a task is mid-flight at the target time, retry every 30s until it succeeds, rather
    than waiting for the next day's window."""
    while True:
        target = next_reset_dt()
        wait_s = max(1.0, (target - datetime.now()).total_seconds())
        await asyncio.sleep(wait_s)
        while True:
            try:
                done = await do_daily_rollover()
            except Exception as e:
                print(f"[rollover] failed: {e}", flush=True)
                done = True  # avoid a tight retry loop on persistent errors
            if done:
                break
            await asyncio.sleep(30)


# ── helpers ──────────────────────────────────────────────────────────────────

def resolve_dir(content: str) -> tuple[str, str]:
    """
    If message starts with 'projectname: task', resolve project subdirectory.
    Returns (working_dir, task_text).
    """
    m = re.match(r'^([\w][\w\-_.]*)\s*:\s*(.+)$', content, re.DOTALL)
    if m:
        name, task = m.group(1), m.group(2).strip()
        candidate = os.path.join(PROJECTS_DIR, name)
        if os.path.isdir(candidate):
            return candidate, task
    return PROJECTS_DIR, content


async def run_claude(task: str, cwd: str) -> str:
    global active_proc, _session_id, _session_start, _session_last_used
    global _prev_session_id, _prev_context_injected

    # Bridge previous day context into the first message of a new session.
    # Normally daily_rollover_loop() already generated this at 04:45; fall back to a
    # lazy fetch here only if the bot was offline at rollover time and it never ran.
    prev_context_block = ""
    if not session_active() and _prev_session_id and not _prev_context_injected:
        summary = load_summary()
        if not summary:
            summary = await fetch_prev_summary(_prev_session_id)
        if summary:
            prev_context_block = (
                f"[Previous day's session summary — for context]\n{summary}\n\n---\n\n"
            )
        _prev_context_injected = True

    # Inject rolling chat history for context continuity
    history = load_chat_history()
    history_block = ""
    if history:
        history_block = format_chat_history(history) + "\n\n---\n\n"

    task_with_ctx = (
        prev_context_block +
        history_block +
        task +
        "\n\nIMPORTANT POINTS TO REMEMBER:\n"
        "- This is a persistent daily session (resets at 04:45); retain and build on prior context from earlier in this session.\n"
        "- CONTEXT RECALL: If the user refers to something you can't find or don't recognize (e.g., 'the prompt', 'that file', 'the error I sent'), "
        "FIRST search back through at least the last 5 exchanges of this session — what the user said and what you replied — "
        "before saying it doesn't exist or asking the user to repeat it.\n"
        "- Search the internet if required to answer accurately or find up-to-date information.\n"
        "- Maintain a history folder inside the project's .claude folder; after any significant change, write a markdown file named as projectName_<short_description>_<YYYYMMDD_HHMM>.md documenting what was done.\n"
        "- USER PROFILE: Read /home/gaurav/.claude/USER.md at the start of each session for context about the user. "
        "Whenever you learn something new about Gaurav (preferences, projects, tech choices, infrastructure details, working style), "
        "append it to /home/gaurav/.claude/USER.md under the '<!-- UPDATES -->' section with today's date. "
        "Keep entries concise — one or two lines per fact.\n"
        "- PERSONALITY: Your name is Claudy Rex. Read /home/gaurav/.claude/CLAUDY_REX.md for your full identity and personality. "
        "Own that name — you are Claudy Rex, Gaurav's engineering AI on the Pi."
    )

    cmd = [CLAUDE_BIN, "--dangerously-skip-permissions", "--output-format", "json"]
    if _model:
        cmd += ["--model", _model]
    if session_active():
        cmd += ["--resume", _session_id]
    cmd += ["-p", task_with_ctx]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env={**os.environ, "TERM": "dumb"},
    )
    active_proc = proc
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return f"Timed out after {TIMEOUT}s."
    finally:
        active_proc = None

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
            if not _session_id:
                _session_start = now
            _session_id = new_sid
            _session_last_used = now
            save_session()
    except (json.JSONDecodeError, AttributeError):
        pass

    if err:
        out += f"\n\n[stderr]\n{err}"

    final_out = out or "(no output)"
    append_chat_history(task, final_out)
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
    load_session()
    load_model()
    print(f"Online as {client.user}", flush=True)
    if _rollover_task is None or _rollover_task.done():
        _rollover_task = asyncio.create_task(daily_rollover_loop())
    ch = client.get_channel(CHANNEL_ID)
    if ch:
        await ch.send("Claude Code bot is online. Send a task or type `!help`.")


@client.event
async def on_message(message: discord.Message):
    global active_task

    if message.author.bot:
        return
    if message.channel.id != CHANNEL_ID:
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
        await message.reply(
            "**Commands**\n"
            "`!help` — show this\n"
            "`!projects` — list projects in PROJECTS_DIR\n"
            "`!cancel` — kill the running task\n"
            "`!status` — check if a task is running\n"
            "`!session` — show current session info\n"
            "`!newsession` — start a fresh Claude session\n"
            "`model <sonnet|opus|haiku|fable|default>` — switch model (also `!model`, no arg shows current)\n\n"
            "**Running a task**\n"
            "Just type your task. Claude runs in `PROJECTS_DIR`.\n"
            "To target a specific project: `projectname: your task here`\n\n"
            "**Sessions**\n"
            "Claude remembers context within each day. "
            "Sessions reset automatically at 04:45 every morning, or use `!newsession`."
        )
        return

    if text.lower() == "!projects":
        await message.reply(f"```\n{list_projects()}\n```")
        return

    if text.lower() == "!session":
        status_line = "Active" if session_active() else "Expired / none"
        await message.reply(f"**Session status:** {status_line}\n{session_age_str()}")
        return

    if text.lower() == "!newsession":
        global _session_id, _session_start, _session_last_used, _prev_context_injected
        if _session_id:
            _prev_session_id = _session_id
        _session_id = None
        _session_start = 0.0
        _session_last_used = 0.0
        _prev_context_injected = False
        save_session()
        await message.reply("Session cleared. Next message starts a fresh conversation.")
        return

    m = re.match(r'^!?model(?:\s+(\S+))?$', text, re.IGNORECASE)
    if m:
        global _model
        arg = m.group(1)
        if not arg:
            current = _model or "default"
            await message.reply(
                f"Current model: `{current}`\n"
                f"Usage: `model <{'|'.join(sorted(MODEL_ALIASES))}|default>`"
            )
            return
        choice = arg.lower()
        if choice == "default":
            _model = None
        elif choice in MODEL_ALIASES:
            _model = choice
        else:
            await message.reply(
                f"Unknown model `{arg}`. Valid: {', '.join(sorted(MODEL_ALIASES))}, default"
            )
            return
        save_model()
        await message.reply(f"Model set to `{_model or 'default'}`. Applies to the next message.")
        return

    if text.lower() in ("!cancel", "!stop"):
        if active_proc:
            active_proc.kill()
        if active_task and not active_task.done():
            active_task.cancel()
            await message.reply("Cancelled.")
        else:
            await message.reply("Nothing is running.")
        return

    if text.lower() == "!status":
        running = active_task and not active_task.done()
        await message.reply("A task is running." if running else "Idle.")
        return

    # ── reject concurrent tasks ──────────────────────────────────────────────
    if active_task and not active_task.done():
        await message.reply("Already running a task. Use `!cancel` to stop it first.")
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
    cwd, task = resolve_dir(text)

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
                output = await run_claude(task, cwd)
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

    active_task = asyncio.create_task(do_task())


if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID or not ALLOWED_IDS:
        print("ERROR: DISCORD_TOKEN, DISCORD_CHANNEL_ID, DISCORD_OWNER_ID must be set in .env")
        sys.exit(1)
    client.run(TOKEN)
