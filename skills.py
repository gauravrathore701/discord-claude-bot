"""
Skills index: tells every channel which skills exist and where their how-to is.

Two sources, scanned fresh on every task (a few dozen small files):
- shared — `~/.claude/skills/<name>/SKILL.md`, usable from every channel
- project — `<cwd>/.claude/skills/`, both native `<name>/SKILL.md` folders and
  the loose `category/<name>.md` files zh-ai-support uses. Claude Code only
  auto-lists the native layout, which is why the bot builds its own index.

`index_block(cwd)` goes into the prompt; `list_text(cwd)` answers `!skills`.
"""

import os
import re
from itertools import takewhile

SHARED_DIR = os.environ.get("SHARED_SKILLS_DIR", os.path.expanduser("~/.claude/skills"))
DESC_MAX = 90           # prompt index: keep each line short, the file has the rest
FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)", re.S)
LABEL_RE = re.compile(r"^(use when|when to use|when|trigger|question shape|question it answers|question)\s*:\s*",
                      re.I)


def _meta(path: str, fallback: str) -> tuple[str, str]:
    """(name, description) from frontmatter; else first prose line of the body."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read(4000)
    except OSError:
        return fallback, ""
    name, desc, body = fallback, "", raw
    m = FRONT_RE.match(raw)
    if m:
        body = m.group(2)
        lines = m.group(1).split("\n")
        for i, line in enumerate(lines):
            if line[:1].isspace():
                continue
            key, _, val = line.partition(":")
            val = val.strip()
            if val in (">", "|", ">-", "|-", ">+", "|+"):     # YAML block scalar
                block = takewhile(lambda x: x[:1].isspace() or not x.strip(), lines[i + 1:])
                val = " ".join(x.strip() for x in block)
            val = val.strip("\"'")
            if key.strip() == "name" and val:
                name = val
            elif key.strip() == "description" and val:
                desc = val
    if not desc:
        desc = next((l.strip() for l in body.split("\n")
                     if l.strip() and not l.lstrip().startswith(("#", "**Tags", "---"))), "")
        desc = LABEL_RE.sub("", desc.replace("**", ""))
    return name, " ".join(desc.split())


def _short(desc: str, cap: int) -> str:
    first = re.split(r"(?<=[.!?])\s", desc, maxsplit=1)[0]
    return first if len(first) <= cap else first[:cap - 1].rstrip() + "…"


def scan(cwd: str | None) -> list[dict]:
    found: list[dict] = []
    if os.path.isdir(SHARED_DIR):
        for entry in sorted(os.listdir(SHARED_DIR)):
            path = os.path.join(SHARED_DIR, entry, "SKILL.md")
            if os.path.isfile(path):
                name, desc = _meta(path, entry)
                found.append({"name": name, "desc": desc, "path": path, "scope": "shared"})

    root = os.path.join(cwd, ".claude", "skills") if cwd else None
    if not root or not os.path.isdir(root) or os.path.realpath(root) == os.path.realpath(SHARED_DIR):
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        if "SKILL.md" in filenames:
            path = os.path.join(dirpath, "SKILL.md")
            name, desc = _meta(path, os.path.basename(dirpath))
            found.append({"name": name, "desc": desc, "path": path, "scope": "project"})
            dirnames[:] = []          # its references/ etc. belong to this skill
            continue
        for fn in sorted(filenames):
            if fn.endswith(".md") and not fn.lower().startswith("readme"):
                path = os.path.join(dirpath, fn)
                name, desc = _meta(path, fn[:-3])
                found.append({"name": name, "desc": desc, "path": path, "scope": "project"})
    return found


def index_block(cwd: str | None) -> str:
    items = scan(cwd)
    if not items:
        return ""
    home = os.path.expanduser("~")

    def short_path(s):
        # project paths relative to the task cwd, shared ones from ~
        if s["scope"] == "project":
            return os.path.relpath(s["path"], cwd)
        return s["path"].replace(home, "~", 1)

    lines =["", "", "SKILLS INDEX (name — when to use — file; read the file before using it):"]
    for scope in ("project", "shared"):
        group = [s for s in items if s["scope"] == scope]
        if group:
            lines.append(f"[{scope}]")
            lines += [f"- {s['name']} — {_short(s['desc'], DESC_MAX)} — "
                      f"{short_path(s)}" for s in group]
    return "\n".join(lines) + "\n"


def list_text(cwd: str | None) -> str:
    items = scan(cwd)
    if not items:
        return "No skills found."
    out = []
    for scope, label in (("project", f"**Project skills** (`{cwd}`)"),
                         ("shared", "**Shared skills** (every channel)")):
        group = [s for s in items if s["scope"] == scope]
        if group:
            out.append(label)
            out += [f"- `{s['name']}` — {_short(s['desc'], 80)}" for s in group]
            out.append("")
    out.append("Ask for one by name, or just describe the task — Claude checks this list first.")
    return "\n".join(out)
