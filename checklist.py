"""
Interactive checklists: a Discord message with one tap-to-tick button per item.

Every checklist is a plain markdown file of `- [ ]` / `- [x]` lines, and that
file is the source of truth — the Discord message is only a view of it.

- Daily task list: the `## Tasks` section of the vault's own daily note,
  `DailyNotes/MMM DD, YYYY.md` (the Obsidian daily-notes folder + format). It
  syncs to the phone, so a tick in Obsidian and a tap in Discord land in the
  same file. Seeded each morning from `DailyNotes/Recurring Tasks.md` plus the
  previous daily note's unticked one-offs, posted to TASKS_CHANNEL_ID at
  TASKS_POST_TIME.
- Ad-hoc lists: Claude puts a ```checklist block in a reply; bot.py swaps it for
  a button message backed by `.claude/checklists/<key>.md`.

Buttons are `discord.ui.DynamicItem`s, so they keep working after a restart:
the custom_id `ck:<key>:<line>:<hash>` carries everything needed to find the
item again. `watch_loop()` re-renders a message whenever its file changes on
disk (Claude or Obsidian editing it), so the view never goes stale.
"""

import asyncio
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta

import discord

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADHOC_DIR = os.path.join(BASE_DIR, ".claude", "checklists")
TRACK_FILE = os.path.join(ADHOC_DIR, "messages.json")

VAULT = os.environ.get("OBSIDIAN_VAULT", "/home/gaurav/Documents/ObsidianVault")
TASKS_DIR = os.environ.get("TASKS_DIR", os.path.join(VAULT, "DailyNotes"))
RECURRING_FILE = os.path.join(TASKS_DIR, "Recurring Tasks.md")
NOTE_TEMPLATE = os.path.join(VAULT, "Templates", "Default.md")
DAILY_NAME = "%b %d, %Y"   # Obsidian daily-notes format "MMM DD, YYYY"
TASKS_HEADING = "## Tasks"
TASKS_CHANNEL_ID = int(os.environ.get("TASKS_CHANNEL_ID", "1508034882645786644"))  # #rex-chat
TASKS_POST_TIME = os.environ.get("TASKS_POST_TIME", "07:00")

MAX_BUTTONS = 25        # Discord hard limit: 5 rows x 5 buttons
LABEL_MAX = 80          # Discord hard limit on a button label
CARRY_LOOKBACK = 7      # days back to look for yesterday's list
WATCH_INTERVAL = 15     # seconds between file-change checks
TRACK_DAYS = 14         # stop watching messages older than this

ITEM_RE = re.compile(r"^(\s*[-*]\s+\[)([ xX])(\]\s+)(.+?)\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s")
BLOCK_RE = re.compile(r"```checklist[^\n]*\n(.*?)```", re.S)

_allowed_ids: set[int] = set()
_client: discord.Client | None = None
_lock = asyncio.Lock()


# ── files ────────────────────────────────────────────────────────────────────

def _h(text: str) -> str:
    return hashlib.sha1(text.strip().encode()).hexdigest()[:8]


def daily_key(d: date) -> str:
    return f"d{d:%Y%m%d}"


def path_for(key: str) -> str:
    if key.startswith("d"):
        d = datetime.strptime(key[1:], "%Y%m%d")
        return os.path.join(TASKS_DIR, d.strftime(DAILY_NAME) + ".md")
    return os.path.join(ADHOC_DIR, f"{key}.md")


def read_items(path: str) -> list[tuple[int, bool, str]]:
    """(line_no, done, text) for every checkbox line."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        return []
    out = []
    for n, line in enumerate(lines):
        m = ITEM_RE.match(line)
        if m:
            out.append((n, m.group(2) != " ", m.group(4)))
    return out


def _write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _title(key: str) -> str:
    path = path_for(key)
    if key.startswith("d"):
        d = datetime.strptime(key[1:], "%Y%m%d")
        return f"📋 Tasks — {d:%a %d %b}"
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("# "):
                    return f"📋 {line[2:].strip()}"
    except OSError:
        pass
    return "📋 Checklist"


def toggle(key: str, line_no: int, h: str) -> bool:
    """Flip one item. Finds it by line number, falls back to the text hash if the
    file was edited and lines moved. False if the item is gone."""
    path = path_for(key)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        return False

    def hit(n):
        m = ITEM_RE.match(lines[n]) if 0 <= n < len(lines) else None
        return m if m and _h(m.group(4)) == h else None

    m = hit(line_no)
    if not m:
        line_no = next((n for n in range(len(lines)) if hit(n)), -1)
        m = hit(line_no)
    if not m:
        return False
    mark = " " if m.group(2) != " " else "x"
    lines[line_no] = f"{m.group(1)}{mark}{m.group(3)}{m.group(4)}"
    _write(path, "\n".join(lines))
    return True


def add_item(key: str, text: str):
    path = path_for(key)
    try:
        with open(path, encoding="utf-8") as f:
            body = f.read()
    except OSError:
        body = ""
    lines = body.split("\n")
    item = f"- [ ] {text.strip()}"
    start = next((n for n, l in enumerate(lines) if l.strip() == TASKS_HEADING), None)
    if start is None:
        if body and not body.endswith("\n"):
            body += "\n"
        _write(path, body + item + "\n")
        return
    end = next((n for n in range(start + 1, len(lines)) if HEADING_RE.match(lines[n])), len(lines))
    last = max((n for n in range(start, end) if lines[n].strip()), default=start)
    lines.insert(last + 1, item)
    _write(path, "\n".join(lines))


def remove_item(key: str, index: int) -> str | None:
    """Drop the index-th item (1-based, as shown in Discord). Returns its text."""
    path = path_for(key)
    items = read_items(path)
    if not 1 <= index <= len(items):
        return None
    line_no, _, text = items[index - 1]
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    del lines[line_no]
    _write(path, "\n".join(lines))
    return text


def ensure_today(today: date | None = None) -> str:
    """Give today's daily note a `## Tasks` section, once: Recurring Tasks.md items,
    then the unticked items of the most recent earlier daily note that are not
    already recurring. Creates the note from Templates/Default.md if Obsidian
    hasn't yet; a note written earlier in the day keeps its content."""
    today = today or date.today()
    key = daily_key(today)
    path = path_for(key)
    try:
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    except OSError:
        existing = None
    if existing is not None and any(l.strip() == TASKS_HEADING for l in existing.split("\n")):
        return key

    if not os.path.exists(RECURRING_FILE):
        _write(RECURRING_FILE,
               "**Tags:** #tasks\n\n"
               "Copied into the `## Tasks` section of every daily note. "
               "One `- [ ] task` per line.\n\n")
    recurring = [t for _, _, t in read_items(RECURRING_FILE)]

    carried: list[str] = []
    for back in range(1, CARRY_LOOKBACK + 1):
        prev = path_for(daily_key(today - timedelta(days=back)))
        if os.path.exists(prev):
            seen = {_h(t) for t in recurring}
            for _, done, t in read_items(prev):
                if not done and _h(t) not in seen:
                    carried.append(t)
                    seen.add(_h(t))
            break

    if existing is None:
        try:
            with open(NOTE_TEMPLATE, encoding="utf-8") as f:
                existing = f.read()
        except OSError:
            existing = "**Tags:**\n"
    body = existing.rstrip("\n") + "\n\n" if existing.strip() else ""
    section = [TASKS_HEADING] + [f"- [ ] {t}" for t in recurring + carried]
    _write(path, body + "\n".join(section) + "\n")
    return key


def new_adhoc(title: str, items: list[str]) -> str:
    key = f"c{int(time.time() * 1000):x}"
    body = [f"# {title}", ""] + [f"- [ ] {t}" for t in items]
    _write(path_for(key), "\n".join(body) + "\n")
    return key


# ── rendering ────────────────────────────────────────────────────────────────

def _label(text: str) -> str:
    # markdown doesn't render on a button; strip the common marks
    text = re.sub(r"[*_`~]", "", text).strip() or "(empty)"
    return text if len(text) <= LABEL_MAX else text[:LABEL_MAX - 1] + "…"


class ToggleButton(discord.ui.DynamicItem[discord.ui.Button],
                   template=r"ck:(?P<key>[a-z0-9]+):(?P<n>\d+):(?P<h>[0-9a-f]{8})"):
    def __init__(self, key: str, line_no: int, h: str, label: str = "…", done: bool = False):
        super().__init__(discord.ui.Button(
            label=label,
            emoji="✅" if done else "⬜",
            style=discord.ButtonStyle.success if done else discord.ButtonStyle.secondary,
            custom_id=f"ck:{key}:{line_no}:{h}",
        ))
        self.key, self.line_no, self.h = key, line_no, h

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["key"], int(match["n"]), match["h"])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in _allowed_ids:
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return
        async with _lock:
            ok = toggle(self.key, self.line_no, self.h)
            content, view = render(self.key)
        await interaction.response.edit_message(content=content, view=view)
        if ok:
            _track(self.key, interaction.channel_id, interaction.message.id)
        else:
            await interaction.followup.send(
                "That item is no longer in the list — refreshed.", ephemeral=True)


def render(key: str) -> tuple[str, discord.ui.View]:
    items = read_items(path_for(key))
    done = sum(1 for _, d, _ in items if d)
    view = discord.ui.View(timeout=None)
    for line_no, d, text in items[:MAX_BUTTONS]:
        view.add_item(ToggleButton(key, line_no, _h(text), _label(text), d))

    head = _title(key)
    if not items:
        return f"**{head}**\nNothing on the list. Add with `!task add <text>`.", view
    status = "🎉 all done" if done == len(items) else f"{done}/{len(items)} done"
    content = f"**{head}** — {status}"
    extra = items[MAX_BUTTONS:]
    if extra:
        content += f"\n{len(extra)} more (no room for buttons — tick in Obsidian):"
        content += "".join(f"\n{'✅' if d else '⬜'} {t}" for _, d, t in extra)
    return content, view


# ── message tracking ─────────────────────────────────────────────────────────

def _load_track() -> dict:
    try:
        with open(TRACK_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_track(data: dict):
    _write(TRACK_FILE, json.dumps(data, indent=2))


def _track(key: str, channel_id: int, message_id: int):
    data = _load_track()
    path = path_for(key)
    data[key] = {
        "channel": channel_id,
        "message": message_id,
        "mtime": os.path.getmtime(path) if os.path.exists(path) else 0,
        "since": data.get(key, {}).get("since", time.time()),
    }
    _save_track(data)


async def post(channel: discord.abc.Messageable, key: str) -> discord.Message:
    """Post a fresh view of `key`. The old message for it, if any, stops being
    watched but its buttons still work."""
    async with _lock:
        content, view = render(key)
        msg = await channel.send(content, view=view)
        _track(key, msg.channel.id, msg.id)
    return msg


async def watch_loop():
    """Re-render a tracked message when its file changes outside a button tap —
    Claude appending a task, or a tick in Obsidian on the phone."""
    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        try:
            data = _load_track()
            changed = False
            for key, t in list(data.items()):
                path = path_for(key)
                if not os.path.exists(path) or time.time() - t.get("since", 0) > TRACK_DAYS * 86400:
                    del data[key]
                    changed = True
                    continue
                mtime = os.path.getmtime(path)
                if mtime == t.get("mtime"):
                    continue
                async with _lock:
                    content, view = render(key)
                    msg = _client.get_partial_messageable(t["channel"]).get_partial_message(t["message"])
                    try:
                        await msg.edit(content=content, view=view)
                    except discord.NotFound:
                        del data[key]
                        changed = True
                        continue
                t["mtime"] = mtime
                changed = True
            if changed:
                _save_track(data)
        except Exception as e:                               # noqa: BLE001 — keep watching
            print(f"[checklist] watch failed: {e}", flush=True)


def _post_dt(day: date) -> datetime:
    h, m = (int(x) for x in TASKS_POST_TIME.split(":"))
    return datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)


async def daily_loop():
    """Post today's task list at TASKS_POST_TIME. If the bot was down at that time,
    post as soon as it comes up (unless today's list was already posted)."""
    while True:
        now = datetime.now()
        today = now.date()
        if now >= _post_dt(today):
            key = daily_key(today)
            if key not in _load_track():
                try:
                    ensure_today(today)
                    ch = _client.get_channel(TASKS_CHANNEL_ID) or await _client.fetch_channel(TASKS_CHANNEL_ID)
                    await post(ch, key)
                    print(f"[checklist] posted daily tasks {key}", flush=True)
                except Exception as e:                       # noqa: BLE001 — retry below
                    print(f"[checklist] daily post failed: {e}", flush=True)
                    await asyncio.sleep(300)
                    continue
            wait = (_post_dt(today + timedelta(days=1)) - datetime.now()).total_seconds()
        else:
            wait = (_post_dt(today) - now).total_seconds()
        await asyncio.sleep(max(1.0, wait))


# ── glue for bot.py ──────────────────────────────────────────────────────────

def setup(client: discord.Client, allowed_ids: set[int]):
    global _client, _allowed_ids
    _client, _allowed_ids = client, allowed_ids
    client.add_dynamic_items(ToggleButton)


def extract_blocks(text: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """Pull ```checklist blocks out of a Claude reply. Returns (text without the
    blocks, [(title, items)])."""
    found = []

    def grab(m):
        title, items = "Checklist", []
        for line in m.group(1).split("\n"):
            s = line.strip()
            if s.startswith("# "):
                title = s[2:].strip()
            elif (im := ITEM_RE.match(s)):
                items.append(im.group(4))
            elif s.startswith(("- ", "* ")):
                items.append(s[2:].strip())
        if items:
            found.append((title, items))
            return ""
        return m.group(0)

    return BLOCK_RE.sub(grab, text).strip(), found


HELP = (
    "**Task list** (no Claude call)\n"
    "`!tasks` — post today's list here\n"
    "`!task add <text>` — add to today\n"
    "`!task rm <n>` — remove item n\n"
    "Tap a button to tick / untick. Tasks live in today's daily note "
    "(`DailyNotes/`), recurring ones in `DailyNotes/Recurring Tasks.md`."
)


async def handle(message: discord.Message, text: str) -> bool:
    """`!tasks` / `!task …` commands. True if handled."""
    parts = text.split(maxsplit=2)
    cmd = parts[0].lower() if parts else ""
    if cmd not in ("!tasks", "!task"):
        return False
    sub = parts[1].lower() if len(parts) > 1 else ""
    arg = parts[2].strip() if len(parts) > 2 else ""
    key = daily_key(date.today())

    if cmd == "!tasks" and not sub:
        async with _lock:
            ensure_today()
        await post(message.channel, key)
        return True

    if sub == "add" and arg:
        async with _lock:
            ensure_today()
            add_item(key, arg[:200])
        # watch_loop refreshes the posted message; post one if today has none yet
        if key not in _load_track():
            await post(message.channel, key)
        else:
            await message.add_reaction("✅")
        return True

    if sub in ("rm", "remove", "del") and arg.isdigit():
        async with _lock:
            gone = remove_item(key, int(arg))
        if gone is None:
            await message.reply(f"No item {arg} on today's list.")
        else:
            await message.reply(f"Removed: {gone}")
        return True

    await message.reply(HELP)
    return True
