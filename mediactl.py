#!/usr/bin/env python3
"""
mediactl — standalone monitor/YouTube control for the Pi.

Any Claude subprocess (any Discord channel) can drive the monitor by shelling
out to this script; it needs NO bot IPC. The discord-claude bot keeps a cage +
Chromium kiosk alive permanently (see media.py); this CLI talks to that same
Chromium over the Chrome DevTools Protocol (CDP, port 9222) and to cage's
Wayland socket via wlr-randr. Both are cross-process, so this works standalone.

Usage:
    mediactl.py play  <query|url>     # audio focus — screen stays dark if it was
    mediactl.py video <query|url>     # wake screen + fullscreen YouTube
    mediactl.py stop                  # back to flip-clock idle screen
    mediactl.py pause | resume
    mediactl.py fullscreen
    mediactl.py wake  | sleep         # HDMI on / off
    mediactl.py status                # JSON-ish one-line state

Design mirrors media.py so behaviour matches the !video / !play bot commands.
Dependency-free (stdlib only) so it runs from any cwd without a venv.
"""
import base64
import glob
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.parse
import urllib.request

UID = 1000
CDP_PORT = int(os.environ.get("MEDIA_CDP_PORT", "9222"))
CDP = f"http://127.0.0.1:{CDP_PORT}"
CAGE_WL_DISPLAY = os.environ.get("MEDIA_WAYLAND_DISPLAY", "wayland-0")
CLOCK_URL = os.environ.get(
    "MEDIA_CLOCK_URL",
    "file://" + os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "flipclock.html"),
)

JS_FIRST_RESULT = """(()=>{
  const a = document.querySelector('ytd-video-renderer a#video-title');
  if (a && a.href) return a.href;
  const bad = 'ytd-ad-slot-renderer,ytd-promoted-video-renderer,ytd-in-feed-ad-layout-renderer';
  const hit = Array.from(document.querySelectorAll('a[href*="/watch?v="]'))
    .find(x => x.href.startsWith('https://www.youtube.com/watch') && !x.closest(bad));
  return hit ? hit.href : null;
})()"""
JS_PLAYING = ("(()=>{const v=document.querySelector('video');"
              "return !!(v && !v.paused && !v.ended && v.readyState > 2)})()")
JS_TITLE = "document.title.replace(/ - YouTube$/, '')"
JS_FULLSCREEN = ("(()=>{ const v=document.querySelector('video');"
                 " if(v){v.requestFullscreen().catch(()=>{});return true;}"
                 " document.querySelector('.ytp-fullscreen-button')?.click(); return false;})()")


# ── CDP over a minimal stdlib websocket ──────────────────────────────────────
def _cdp_targets():
    with urllib.request.urlopen(f"{CDP}/json", timeout=5) as r:
        return json.loads(r.read())


def _page_ws():
    page = next((t for t in _cdp_targets() if t.get("type") == "page"), None)
    return page["webSocketDebuggerUrl"] if page else None


def _ws_eval(js, user_gesture=False, want_result=True, timeout=12):
    ws_url = _page_ws()
    if not ws_url:
        return None
    p = urllib.parse.urlparse(ws_url)
    sock = socket.create_connection((p.hostname, p.port), timeout=timeout)
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET {p.path} HTTP/1.1\r\nHost: {p.hostname}:{p.port}\r\n"
                      "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += sock.recv(4096)

        payload = json.dumps({"id": 1, "method": "Runtime.evaluate",
                              "params": {"expression": js, "returnByValue": True,
                                         "userGesture": user_gesture}}).encode()
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            hdr = bytes([0x81, 0x80 | n])
        else:
            hdr = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

        if not want_result:
            time.sleep(0.2)
            return None
        return _ws_read_result(sock, timeout)
    finally:
        sock.close()


def _ws_read_result(sock, timeout):
    sock.settimeout(timeout)
    deadline = time.monotonic() + timeout
    data = b""
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        frame = _decode_ws_text(data)
        if frame is not None:
            try:
                msg = json.loads(frame)
                if msg.get("id") == 1:
                    return msg.get("result", {}).get("result", {}).get("value")
            except json.JSONDecodeError:
                data = b""  # keep reading
    return None


def _decode_ws_text(data):
    """Decode one unmasked server text frame; returns str or None if incomplete."""
    if len(data) < 2:
        return None
    ln = data[1] & 0x7F
    off = 2
    if ln == 126:
        if len(data) < 4:
            return None
        ln = struct.unpack(">H", data[2:4])[0]; off = 4
    elif ln == 127:
        if len(data) < 10:
            return None
        ln = struct.unpack(">Q", data[2:10])[0]; off = 10
    if len(data) < off + ln:
        return None
    return data[off:off + ln].decode("utf-8", "replace")


def _navigate(url):
    _ws_eval(f"location.href = {json.dumps(url)}", want_result=False)


def _poll(js, total=20.0, every=0.5):
    deadline = time.monotonic() + total
    while time.monotonic() < deadline:
        v = _ws_eval(js)
        if v:
            return v
        time.sleep(every)
    return None


def _cdp_up():
    try:
        with urllib.request.urlopen(f"{CDP}/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# ── HDMI / display ───────────────────────────────────────────────────────────
def hdmi_connector():
    for path in sorted(glob.glob("/sys/class/drm/card*-HDMI-A-*")):
        try:
            with open(f"{path}/status") as f:
                if f.read().strip() != "connected":
                    continue
        except OSError:
            continue
        conn = os.path.basename(path).split("-", 1)[1]
        return conn
    return None


def _wlr_randr(conn, on):
    import subprocess
    env = {**os.environ,
           "XDG_RUNTIME_DIR": f"/run/user/{UID}",
           "WAYLAND_DISPLAY": CAGE_WL_DISPLAY}
    r = subprocess.run(["wlr-randr", "--output", conn, "--on" if on else "--off"],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0


# ── commands ─────────────────────────────────────────────────────────────────
def cmd_play(query, video=False):
    if not _cdp_up():
        return err("kiosk/CDP not up — is the discord-claude bot running?")
    conn = hdmi_connector()
    if video and not conn:
        return err("no HDMI output detected")

    q = query.strip()
    if q.startswith(("http://", "https://")):
        url = q
    else:
        _navigate("https://www.youtube.com/results?search_query="
                  + urllib.parse.quote_plus(q))
        url = _poll(JS_FIRST_RESULT, total=20)
        if not url:
            return err(f"no YouTube result for: {q}")

    if video and conn:
        _wlr_randr(conn, True)
    _navigate(url)
    started = _poll(JS_PLAYING, total=25)
    title = _ws_eval(JS_TITLE) or q
    if video and started:
        time.sleep(1)
        _ws_eval(JS_FULLSCREEN, user_gesture=True)
    return ok(("video" if video else "audio"), title=title,
              playing=bool(started),
              note=None if started else "loaded, playback not confirmed (ad/consent?)")


def cmd_stop():
    if not _cdp_up():
        return err("kiosk/CDP not up")
    _navigate(CLOCK_URL)
    return ok("stopped", note="back to clock")


def cmd_pause():
    r = _ws_eval("(()=>{const v=document.querySelector('video');"
                 "if(!v||v.paused)return false;v.pause();return true})()")
    return ok("paused") if r else err("nothing to pause")


def cmd_resume():
    r = _ws_eval("(()=>{const v=document.querySelector('video');"
                 "if(!v||!v.paused)return false;v.play();return true})()")
    return ok("resumed") if r else err("nothing to resume")


def cmd_fullscreen():
    r = _ws_eval(JS_FULLSCREEN, user_gesture=True)
    return ok("fullscreen", requested=bool(r))


def cmd_display(on):
    conn = hdmi_connector()
    if not conn:
        return err("no HDMI output detected")
    good = _wlr_randr(conn, on)
    if good and on and _cdp_up():
        # wake shows the clock if nothing is playing
        if not _ws_eval(JS_PLAYING):
            _navigate(CLOCK_URL)
    return ok(f"{conn} {'on' if on else 'off'}") if good else err(f"couldn't switch {conn}")


def cmd_status():
    if not _cdp_up():
        return err("kiosk/CDP not up")
    playing = _ws_eval(JS_PLAYING)
    title = _ws_eval(JS_TITLE)
    conn = hdmi_connector()
    return ok("status", playing=bool(playing), title=title, hdmi=conn or "disconnected")


# ── output helpers ───────────────────────────────────────────────────────────
def ok(action, **kw):
    kw = {k: v for k, v in kw.items() if v is not None}
    print(json.dumps({"ok": True, "action": action, **kw}))
    return 0


def err(msg):
    print(json.dumps({"ok": False, "error": msg}))
    return 1


USAGE = ("mediactl.py play|video <query|url> | stop | pause | resume | "
         "fullscreen | wake | sleep | status")


def main(argv):
    if not argv:
        print(USAGE); return 2
    cmd, rest = argv[0], argv[1:]
    arg = " ".join(rest).strip()
    if cmd == "play":
        return cmd_play(arg, video=False) if arg else err("play needs a query/url")
    if cmd in ("video", "playvideo"):
        return cmd_play(arg, video=True) if arg else err("video needs a query/url")
    if cmd in ("stop", "mstop"):
        return cmd_stop()
    if cmd == "pause":
        return cmd_pause()
    if cmd == "resume":
        return cmd_resume()
    if cmd in ("fullscreen", "fs"):
        return cmd_fullscreen()
    if cmd in ("wake", "screenon"):
        return cmd_display(True)
    if cmd in ("sleep", "screenoff"):
        return cmd_display(False)
    if cmd in ("status", "np"):
        return cmd_status()
    print(USAGE); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
