#!/usr/bin/env python3
"""
Browser-based media playback + HDMI display control for the Discord bot.

v4 — always-on flip clock idle screen.

cage + Chromium start at bot startup showing a local flip-clock page
(static/flipclock.html). On !play/!video the browser navigates to YouTube;
on !stop it navigates back to the clock. cage stays alive permanently so the
monitor always shows the clock when nothing plays. Screen blanks after
MEDIA_IDLE_TIMEOUT seconds (wlr-randr off); !wake restores it and re-shows
the clock.

Display control:
  - cage running  → `wlr-randr --output <conn> --on/--off` against cage's socket
  - cage stopped  → blanking via a held `kmsblank --device=<card>` process
kmsblank holds DRM master, so it must die before cage can start.

Audio goes to the default PipeWire sink (monitor HDMI).
"""
import asyncio
import glob
import json
import os
import signal
import time
import urllib.parse

import aiohttp

UID = 1000
ENV = {
    **{k: v for k, v in os.environ.items() if k != "WAYLAND_DISPLAY"},
    "XDG_RUNTIME_DIR": f"/run/user/{UID}",
    "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{UID}/bus",
}
# cage creates its own socket; wayland-0 since it's the only compositor here.
CAGE_WL_DISPLAY = os.environ.get("MEDIA_WAYLAND_DISPLAY", "wayland-0")
CAGE_ENV = {**ENV, "WAYLAND_DISPLAY": CAGE_WL_DISPLAY}

CAGE = os.environ.get("MEDIA_CAGE_BIN", "/usr/bin/cage")
CHROMIUM = os.environ.get("MEDIA_BROWSER_BIN", "/usr/bin/chromium")
KMSBLANK = os.environ.get("MEDIA_KMSBLANK_BIN", "/usr/bin/kmsblank")
CDP_PORT = int(os.environ.get("MEDIA_CDP_PORT", "9222"))
CDP = f"http://127.0.0.1:{CDP_PORT}"
PROFILE_DIR = os.path.expanduser("~/.config/chromium-media")

IDLE_TIMEOUT = int(os.environ.get("MEDIA_IDLE_TIMEOUT", str(30 * 60)))  # seconds
IDLE_POLL = 60
WATCH_POLL = 10  # ad-skip / activity watcher interval while media is up

CLOCK_URL = os.environ.get(
    "MEDIA_CLOCK_URL",
    "file://" + os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "flipclock.html"),
)

CHROMIUM_FLAGS = [
    "--kiosk", "--noerrdialogs", "--disable-infobars", "--no-first-run",
    "--ozone-platform=wayland",
    "--autoplay-policy=no-user-gesture-required",
    # basic = plaintext profile store; keeps gnome-keyring from popping a
    # "choose password for new keyring" dialog on a screen with no keyboard
    "--password-store=basic",
    f"--remote-debugging-port={CDP_PORT}",
    f"--user-data-dir={PROFILE_DIR}",
]

# Organic results only: ytd-video-renderer skips ad slots. The fallback scans
# all /watch links but drops ones inside ad renderers or off-site redirects.
JS_FIRST_RESULT = """(()=>{
  const a = document.querySelector('ytd-video-renderer a#video-title');
  if (a && a.href) return a.href;
  const bad = 'ytd-ad-slot-renderer,ytd-promoted-video-renderer,ytd-in-feed-ad-layout-renderer';
  const hit = Array.from(document.querySelectorAll('a[href*="/watch?v="]'))
    .find(x => x.href.startsWith('https://www.youtube.com/watch') && !x.closest(bad));
  return hit ? hit.href : null;
})()"""
JS_PLAYING = (
    "(()=>{const v=document.querySelector('video');"
    "return !!(v && !v.paused && !v.ended && v.readyState > 2)})()"
)
JS_SKIP_AD = (
    "document.querySelector('.ytp-skip-ad-button,.ytp-ad-skip-button,"
    ".ytp-ad-skip-button-modern')?.click()"
)
JS_TITLE = "document.title.replace(/ - YouTube$/, '')"
JS_FULLSCREEN = (
    "(()=>{ const v=document.querySelector('video');"
    " if(v){v.requestFullscreen().catch(()=>{});return true;}"
    " document.querySelector('.ytp-fullscreen-button')?.click(); return false;})()"
)


def hdmi_connector() -> tuple[str, str] | None:
    """Return (connector_name, /dev/dri/cardN) for the connected HDMI, from sysfs."""
    for path in sorted(glob.glob("/sys/class/drm/card*-HDMI-A-*")):
        try:
            with open(f"{path}/status") as f:
                if f.read().strip() != "connected":
                    continue
        except OSError:
            continue
        base = os.path.basename(path)          # e.g. card1-HDMI-A-2
        card, conn = base.split("-", 1)        # "card1", "HDMI-A-2"
        return conn, f"/dev/dri/{card}"
    return None


class MediaPlayer:
    def __init__(self, log=print):
        self.log = log
        self.proc: asyncio.subprocess.Process | None = None   # cage (chromium inside)
        self.blank_proc: asyncio.subprocess.Process | None = None  # kmsblank
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

    async def _eval(self, js: str, timeout=10, user_gesture=False):
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
                        "params": {"expression": js, "returnByValue": True,
                                   "userGesture": user_gesture},
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

    # ── browser (cage) lifecycle ─────────────────────────────────────────────
    def browser_alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def _ensure_browser(self) -> bool:
        if self.browser_alive() and await self._cdp_up():
            return True
        await self._kill_browser()
        await self._kill_blank()  # kmsblank holds DRM master; cage needs it
        self.proc = await asyncio.create_subprocess_exec(
            CAGE, "--", CHROMIUM, *CHROMIUM_FLAGS, CLOCK_URL,
            env=ENV, start_new_session=True,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        for _ in range(40):  # up to 20s: cage + chromium + CDP
            await asyncio.sleep(0.5)
            if await self._cdp_up():
                self.display_on = True  # cage lights the output when it takes over
                self._ensure_idle_loop()
                return True
            if self.proc.returncode is not None:
                break
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
        self.display_on = True  # console is visible again once cage exits

    # ── kmsblank lifecycle (console blanking while no compositor runs) ──────
    def _blank_alive(self) -> bool:
        return self.blank_proc is not None and self.blank_proc.returncode is None

    async def _start_blank(self, card: str) -> bool:
        if self._blank_alive():
            return True
        self.blank_proc = await asyncio.create_subprocess_exec(
            KMSBLANK, f"--device={card}",
            env=ENV, stdin=asyncio.subprocess.DEVNULL,  # waits for enter = stays blank
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.sleep(1)
        return self.blank_proc.returncode is None

    async def _kill_blank(self):
        if self._blank_alive():
            self.blank_proc.terminate()
            try:
                await asyncio.wait_for(self.blank_proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.blank_proc.kill()
        self.blank_proc = None

    # ── display control ──────────────────────────────────────────────────────
    async def _wlr_randr(self, conn: str, on: bool) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "wlr-randr", "--output", conn, "--on" if on else "--off",
            env=CAGE_ENV,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    async def display(self, on: bool) -> tuple[bool, str]:
        hdmi = hdmi_connector()
        if not hdmi:
            return False, "No HDMI output detected — is the monitor plugged in?"
        conn, card = hdmi
        if self.browser_alive():
            ok = await self._wlr_randr(conn, on)
            if ok and on and not self.title:
                await self._navigate(CLOCK_URL)   # wake → show clock
            how = "compositor"
        elif on:
            await self._kill_blank()
            ok, how = True, "console"
        else:
            ok = await self._start_blank(card)
            how = "console"
        if ok:
            self.display_on = on
            self.touch()
            return True, f"{conn} → {'on' if on else 'off'} ({how})"
        return False, f"Couldn't switch {conn} {'on' if on else 'off'}"

    # ── playback ─────────────────────────────────────────────────────────────
    async def play(self, query: str, video: bool = False) -> tuple[bool, str]:
        async with self._lock:
            if video and not hdmi_connector():
                return False, "Can't show video — no HDMI output detected."

            was_off = not self.display_on
            if not await self._ensure_browser():
                return False, "Browser failed to start (cage/CDP never came up)."

            # audio focus keeps the screen dark if it was dark before
            if not video and was_off:
                hdmi = hdmi_connector()
                if hdmi and await self._wlr_randr(hdmi[0], False):
                    self.display_on = False

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

            if video and not self.display_on:
                hdmi = hdmi_connector()
                if hdmi:
                    await self._wlr_randr(hdmi[0], True)
                    self.display_on = True

            await self._navigate(url)
            started = await self._poll_eval(JS_PLAYING, total=25)
            title = await self._eval(JS_TITLE) or q

            if started:
                # fullscreen always — kiosk flag keeps browser full-window but
                # the YouTube player itself still needs requestFullscreen()
                await asyncio.sleep(1)
                await self._eval(JS_FULLSCREEN, user_gesture=True)

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
            self.title = None
            self.is_video = False
            if self.browser_alive():
                await self._navigate(CLOCK_URL)   # back to clock; cage stays alive
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
            if self.title and self.browser_alive():
                self.log("[media] idle timeout — returning to clock")
                self.title = None
                self.is_video = False
                await self._navigate(CLOCK_URL)
            if self.display_on:
                self.log("[media] idle timeout — blanking HDMI")
                await self.display(False)

    # ── startup ──────────────────────────────────────────────────────────────
    async def startup(self):
        """Start cage+Chromium at the clock screen. Non-fatal if a desktop already owns DRM."""
        if self.browser_alive():
            return
        self.log("[media] startup: launching clock screen")
        ok = await self._ensure_browser()
        if not ok:
            self.log("[media] startup: cage failed to start (desktop may own DRM — will retry on first !play)")

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
        tail = f" (blanks in ~{left}m)" if self.display_on else ""
        if self.browser_alive():
            return f"🕐 Clock screen active.\n{disp}{tail}"
        return f"⏹ Nothing playing (clock offline).\n{disp}{tail}"
