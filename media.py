#!/usr/bin/env python3
"""
Browser-based media playback + HDMI display control for the Discord bot.

v2 — Chromium kiosk + CDP (replaces the v1 yt-dlp|cvlc pipeline at Gaurav's request:
he wants real YouTube in a browser on the monitor).

The Pi 5 boots to a labwc Wayland desktop (auto-login as gaurav, uid 1000); the bot
runs as the same user, so it launches Chromium into that session and drives it over
the DevTools protocol (CDP, port 9222): navigate to YouTube, click nothing, read the
<video> element, pause/resume it. No LLM or keystroke faking in the loop.

Display on/off stays `wlr-randr --output HDMI-A-2 --on/--off` (vcgencmd display_power
is not registered on Pi 5). Idle blanking: after IDLE_TIMEOUT with nothing playing,
the HDMI output is blanked AND the browser is closed to free RAM.

Audio goes to the default PipeWire sink — the monitor's HDMI sink ("Built-in Audio
Digital Stereo (HDMI)"), which appears once the monitor is attached. If it's missing
after a hotplug, `systemctl --user restart wireplumber` rescans it.
"""
import asyncio
import json
import os
import signal
import time
import urllib.parse

import aiohttp

UID = 1000
WL_ENV = {
    **os.environ,
    "XDG_RUNTIME_DIR": f"/run/user/{UID}",
    "WAYLAND_DISPLAY": os.environ.get("MEDIA_WAYLAND_DISPLAY", "wayland-0"),
    "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{UID}/bus",
}

CHROMIUM = os.environ.get("MEDIA_BROWSER_BIN", "/usr/bin/chromium")
CDP_PORT = int(os.environ.get("MEDIA_CDP_PORT", "9222"))
CDP = f"http://127.0.0.1:{CDP_PORT}"
PROFILE_DIR = os.path.expanduser("~/.config/chromium-media")  # separate from openclaw's profile

IDLE_TIMEOUT = int(os.environ.get("MEDIA_IDLE_TIMEOUT", str(30 * 60)))  # seconds
IDLE_POLL = 60
WATCH_POLL = 10  # ad-skip / activity watcher interval while media is up

BROWSER_FLAGS = [
    "--kiosk", "--noerrdialogs", "--disable-infobars", "--no-first-run",
    # Explicit wayland: with --remote-debugging-port set, the "auto" hint
    # falls back to X11 (no X server here) and Chromium exits immediately.
    "--ozone-platform=wayland",
    "--autoplay-policy=no-user-gesture-required",
    f"--remote-debugging-port={CDP_PORT}",
    f"--user-data-dir={PROFILE_DIR}",
]

JS_FIRST_RESULT = (
    "document.querySelector('ytd-video-renderer a#video-title')?.href || null"
)
JS_PLAYING = (
    "(()=>{const v=document.querySelector('video');"
    "return !!(v && !v.paused && !v.ended && v.readyState > 2)})()"
)
JS_SKIP_AD = (
    "document.querySelector('.ytp-skip-ad-button,.ytp-ad-skip-button,"
    ".ytp-ad-skip-button-modern')?.click()"
)
JS_TITLE = "document.title.replace(/ - YouTube$/, '')"


class MediaPlayer:
    def __init__(self, log=print):
        self.log = log
        self.proc: asyncio.subprocess.Process | None = None  # chromium
        self.title: str | None = None
        self.is_video = False
        self.started_at = 0.0
        self.last_activity = time.monotonic()
        self.display_on = True
        self._lock = asyncio.Lock()
        self._idle_task: asyncio.Task | None = None
        self._watch_task: asyncio.Task | None = None

    def touch(self):
        self.last_activity = time.monotonic()

    # ── CDP plumbing ─────────────────────────────────────────────────────────
    async def _cdp_up(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{CDP}/json/version",
                                 timeout=aiohttp.ClientTimeout(total=2)) as r:
                    return r.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def _eval(self, js: str, timeout=10):
        """Runtime.evaluate on the first page target; returns the JS value or None."""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{CDP}/json",
                                 timeout=aiohttp.ClientTimeout(total=5)) as r:
                    targets = await r.json()
                page = next((t for t in targets if t.get("type") == "page"), None)
                if not page:
                    return None
                async with s.ws_connect(page["webSocketDebuggerUrl"]) as ws:
                    await ws.send_json({
                        "id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": js, "returnByValue": True},
                    })
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        msg = await asyncio.wait_for(ws.receive_json(),
                                                     deadline - time.monotonic())
                        if msg.get("id") == 1:
                            return msg.get("result", {}).get("result", {}).get("value")
        except (aiohttp.ClientError, asyncio.TimeoutError, StopIteration,
                KeyError, json.JSONDecodeError):
            return None

    async def _navigate(self, url: str):
        await self._eval(f"location.href = {json.dumps(url)}")

    async def _poll_eval(self, js: str, total=15.0, every=0.5):
        """Re-evaluate js until it returns a truthy value or the deadline passes."""
        deadline = time.monotonic() + total
        while time.monotonic() < deadline:
            val = await self._eval(js)
            if val:
                return val
            await asyncio.sleep(every)
        return None

    # ── browser lifecycle ────────────────────────────────────────────────────
    def browser_alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def _ensure_browser(self) -> bool:
        if self.browser_alive() and await self._cdp_up():
            return True
        await self._kill_browser()
        self.proc = await asyncio.create_subprocess_exec(
            CHROMIUM, *BROWSER_FLAGS, "about:blank",
            env=WL_ENV, start_new_session=True,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        for _ in range(30):  # up to 15s for CDP to come up
            await asyncio.sleep(0.5)
            if await self._cdp_up():
                self._ensure_idle_loop()
                return True
        await self._kill_browser()
        return False

    async def _kill_browser(self):
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        if self.proc and self.proc.returncode is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        self.proc = None
        self.title = None
        self.is_video = False

    # ── display control ──────────────────────────────────────────────────────
    async def hdmi_output(self) -> str | None:
        proc = await asyncio.create_subprocess_exec(
            "wlr-randr", env=WL_ENV,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        for line in out.decode(errors="replace").splitlines():
            if line and not line[0].isspace() and line.split()[0].upper().startswith("HDMI"):
                return line.split()[0]
        return None

    async def display(self, on: bool) -> tuple[bool, str]:
        conn = await self.hdmi_output()
        if not conn:
            return False, "No HDMI output detected — is the monitor plugged in?"
        proc = await asyncio.create_subprocess_exec(
            "wlr-randr", "--output", conn, "--on" if on else "--off",
            env=WL_ENV, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        ok = proc.returncode == 0
        if ok:
            self.display_on = on
            self.touch()
        return ok, (f"{conn} → {'on' if on else 'off'}" if ok else "wlr-randr failed")

    # ── playback ─────────────────────────────────────────────────────────────
    async def play(self, query: str, video: bool = False) -> tuple[bool, str]:
        async with self._lock:
            if video:
                ok, msg = await self.display(True)
                if not ok:
                    return False, f"Can't show video — {msg}"

            if not await self._ensure_browser():
                return False, "Browser failed to start (CDP never came up)."

            q = query.strip()
            if q.startswith(("http://", "https://")):
                url = q
            else:
                await self._navigate(
                    "https://www.youtube.com/results?search_query="
                    + urllib.parse.quote_plus(q)
                )
                url = await self._poll_eval(JS_FIRST_RESULT, total=20)
                if not url:
                    return False, f"No YouTube result found for: {q}"

            await self._navigate(url)
            started = await self._poll_eval(JS_PLAYING, total=25)
            title = await self._eval(JS_TITLE) or q

            self.title = title
            self.is_video = video
            self.started_at = time.monotonic()
            self.touch()
            self._ensure_idle_loop()
            if self._watch_task is None or self._watch_task.done():
                self._watch_task = asyncio.create_task(self._watch_loop())
            self.log(f"[media] playing ({'video' if video else 'audio'}): {title}")
            if not started:
                return True, f"{title} — loaded, but playback hasn't started yet (ad or consent screen?)"
            return True, title

    async def pause(self) -> bool:
        r = await self._eval("(()=>{const v=document.querySelector('video');"
                             "if(!v||v.paused)return false;v.pause();return true})()")
        self.touch()
        return bool(r)

    async def resume(self) -> bool:
        r = await self._eval("(()=>{const v=document.querySelector('video');"
                             "if(!v||!v.paused)return false;v.play();return true})()")
        self.touch()
        return bool(r)

    async def stop(self) -> bool:
        async with self._lock:
            was = bool(self.title) and await self._eval(JS_PLAYING)
            if self.browser_alive():
                await self._navigate("about:blank")
            self.title = None
            self.is_video = False
            self.touch()
            return bool(was)

    # ── watcher: ad-skip + activity ──────────────────────────────────────────
    async def _watch_loop(self):
        while self.browser_alive():
            await asyncio.sleep(WATCH_POLL)
            await self._eval(JS_SKIP_AD, timeout=5)
            if await self._eval(JS_PLAYING, timeout=5):
                self.touch()

    # ── idle blanking ────────────────────────────────────────────────────────
    def _ensure_idle_loop(self):
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = asyncio.create_task(self._idle_loop())

    async def _idle_loop(self):
        while True:
            await asyncio.sleep(IDLE_POLL)
            if (time.monotonic() - self.last_activity) < IDLE_TIMEOUT:
                continue
            if self.browser_alive():
                self.log("[media] idle timeout — closing browser")
                await self._kill_browser()
            if self.display_on:
                self.log("[media] idle timeout — blanking HDMI output")
                await self.display(False)

    # ── status ───────────────────────────────────────────────────────────────
    async def status(self) -> str:
        disp = f"Display: {'on' if self.display_on else 'off'}"
        if self.browser_alive() and self.title:
            playing = await self._eval(JS_PLAYING)
            state = "▶ Playing" if playing else "⏸ Paused/stalled"
            elapsed = int(time.monotonic() - self.started_at)
            m, s = divmod(elapsed, 60)
            mode = "video" if self.is_video else "audio"
            return f"{state} ({mode}): **{self.title}** — {m}m{s:02d}s\n{disp}"
        idle = int(time.monotonic() - self.last_activity)
        left = max(0, IDLE_TIMEOUT - idle) // 60
        tail = f" (browser+screen close in ~{left}m if idle)" if (self.display_on or self.browser_alive()) else ""
        return f"⏹ Nothing playing.\n{disp}{tail}"
