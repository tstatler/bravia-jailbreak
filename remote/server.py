#!/usr/bin/env python3
"""
Sony Bravia Web Remote & Control Center — Zero-Dependency HTTP/ADB Server
"""
import json
import os
import re
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
STATIC_DIR = SCRIPT_DIR / "static"
ENV_FILE = ROOT_DIR / ".bravia.env"

KEYCODE_MAP = {
    "UP": "KEYCODE_DPAD_UP",
    "DOWN": "KEYCODE_DPAD_DOWN",
    "LEFT": "KEYCODE_DPAD_LEFT",
    "RIGHT": "KEYCODE_DPAD_RIGHT",
    "CENTER": "KEYCODE_DPAD_CENTER",
    "OK": "KEYCODE_DPAD_CENTER",
    "BACK": "KEYCODE_BACK",
    "HOME": "KEYCODE_HOME",
    "MENU": "KEYCODE_MENU",
    "TV_INPUT": "KEYCODE_TV_INPUT",
    "POWER": "KEYCODE_POWER",
    "SLEEP": "KEYCODE_SLEEP",
    "WAKEUP": "KEYCODE_WAKEUP",
    "VOL_UP": "KEYCODE_VOLUME_UP",
    "VOL_DOWN": "KEYCODE_VOLUME_DOWN",
    "MUTE": "KEYCODE_VOLUME_MUTE",
    "PLAY_PAUSE": "KEYCODE_MEDIA_PLAY_PAUSE",
    "REWIND": "KEYCODE_MEDIA_REWIND",
    "FAST_FORWARD": "KEYCODE_MEDIA_FAST_FORWARD",
    "STOP": "KEYCODE_MEDIA_STOP",
    "NEXT": "KEYCODE_MEDIA_NEXT",
    "PREV": "KEYCODE_MEDIA_PREVIOUS",
    "DEL": "KEYCODE_DEL",
    "ENTER": "KEYCODE_ENTER",
    "CAPTIONS": "KEYCODE_CAPTIONS",
    "SETTINGS": "KEYCODE_SETTINGS",
    "GUIDE": "KEYCODE_GUIDE",
    "CHANNEL_UP": "KEYCODE_CHANNEL_UP",
    "CHANNEL_DOWN": "KEYCODE_CHANNEL_DOWN",
}

SWEEPABLE_APPS = [
    "com.netflix.ninja",
    "com.tubitv",
    "com.hulu.livingroomplus",
    "com.amazon.amazonvideo.livingroom",
    "com.disney.disneyplus",
    "com.hbo.hbonow",
    "com.peacocktv.peacockandroid",
    "com.spotify.tv.android",
    "org.smarttube.stable",
    "com.phlox.tvwebbrowser",
    "com.google.android.youtube.tv",
    "com.google.android.youtube.tvunplugged",
    "tv.pluto.android",
    "com.kanopy.tvapp",
    "com.collegehumor.chdropout",
    "com.fubo.firetv.screen",
    "com.roku.web.trc",
    "com.turner.tnt.android.networkapp",
    "com.android.vending",
]

APP_FRIENDLY_NAMES = {
    "org.smarttube.stable": "SmartTube",
    "com.phlox.tvwebbrowser": "TV Bro Browser",
    "com.netflix.ninja": "Netflix",
    "com.tubitv": "Tubi TV",
    "com.hulu.livingroomplus": "Hulu",
    "com.hbo.hbonow": "Max (HBO)",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.peacocktv.peacockandroid": "Peacock",
    "com.spotify.tv.android": "Spotify",
    "tv.pluto.android": "Pluto TV",
    "com.google.android.youtube.tv": "YouTube",
    "com.google.android.youtube.tvunplugged": "YouTube TV",
    "com.android.tv": "Live Antenna TV",
    "com.spocky.projengmenu": "Projectivy Home",
    "com.android.tv.settings": "TV Settings",
    "com.android.vending": "Play Store",
    "com.google.android.gms": "Google Play Services",
    "com.google.android.apps.mediashell": "Chromecast Receiver",
    "system_server": "Android System Server",
    "com.android.systemui": "System UI",
    "com.android.providers.tv": "Live TV EPG Provider",
    "com.google.android.inputmethod.latin": "On-Screen Keyboard",
    "com.sony.dtv.smartui": "Sony Bravia UI",
}


def load_env():
    cfg = {
        "TV_NAME": "BRAVIA",
        "TV_MDNS_HOST": "Android.local.",
        "TV_MAC": "",
        "TV_FALLBACK_IP": "",
        "ADB_PORT": "5555",
    }
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.split("#", 1)[0].strip().strip('"').strip("'")
            cfg[k.strip()] = v
    if os.environ.get("TV_IP"):
        cfg["TV_FALLBACK_IP"] = os.environ["TV_IP"]
    return cfg


ENV = load_env()


def get_adb_target():
    ip = ENV.get("TV_FALLBACK_IP", "")
    port = ENV.get("ADB_PORT", "5555")
    return f"{ip}:{port}"


def run_adb(args, timeout=6):
    target = get_adb_target()
    cmd = ["adb", "-s", target] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0 and "not found" in (res.stderr or ""):
            subprocess.run(["adb", "connect", target], capture_output=True, text=True, timeout=4)
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode == 0, (res.stdout or "").strip(), (res.stderr or "").strip()
    except Exception as exc:
        return False, "", str(exc)


def send_wol():
    mac_str = ENV.get("TV_MAC", "").replace(":", "").replace("-", "").strip()
    if len(mac_str) != 12:
        return
    try:
        mac_bytes = bytes.fromhex(mac_str)
        magic = b"\xff" * 6 + mac_bytes * 16
        ip_parts = ENV.get("TV_FALLBACK_IP", "").split(".")
        bcast = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.255" if len(ip_parts) == 4 else "255.255.255.255"
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(magic, (bcast, 9))
        s.close()
    except Exception:
        pass


def escape_adb_text(text: str) -> str:
    out = []
    for ch in text:
        if ch == " ":
            out.append("%s")
        elif ch in r'\"`$&|;<>()*?!~#[]{}':
            out.append("\\" + ch)
        elif ch == "'":
            out.append("\\'")
        else:
            out.append(ch)
    return "".join(out)


def parse_status():
    ok, out, err = run_adb([
        "shell",
        "grep -E 'MemTotal|MemFree|MemAvailable|Cached|SwapTotal|SwapFree' /proc/meminfo; "
        "echo '===PS==='; "
        "ps -A -o PID,USER,RSS,ARGS | awk '$3 > 25000' | sort -k3 -rn | head -n 12; "
        "echo '===MEDIA==='; "
        "dumpsys media_session"
    ], timeout=6)

    if not ok:
        return {
            "connected": False,
            "tv_name": ENV.get("TV_NAME", "BRAVIA"),
            "target": get_adb_target(),
            "error": err or "TV unreachable or in standby",
        }

    parts = out.split("===PS===")
    mem_raw = parts[0] if len(parts) > 0 else ""
    rest = parts[1] if len(parts) > 1 else ""
    ps_parts = rest.split("===MEDIA===")
    ps_raw = ps_parts[0] if len(ps_parts) > 0 else ""
    media_raw = ps_parts[1] if len(ps_parts) > 1 else ""

    # 1. Parse /proc/meminfo
    mem = {}
    for line in mem_raw.splitlines():
        m = re.match(r"^(\w+):\s+(\d+)", line.strip())
        if m:
            mem[m.group(1)] = int(m.group(2))

    total_mb = round(mem.get("MemTotal", 2097152) / 1024)
    avail_mb = round(mem.get("MemAvailable", 0) / 1024)
    used_mb = max(0, total_mb - avail_mb)
    swap_total_mb = round(mem.get("SwapTotal", 614396) / 1024)
    swap_free_mb = round(mem.get("SwapFree", 0) / 1024)
    swap_used_mb = max(0, swap_total_mb - swap_free_mb)

    # 2. Parse top processes
    processes = []
    for line in ps_raw.splitlines():
        cols = line.strip().split(None, 3)
        if len(cols) < 4 or not cols[2].isdigit():
            continue
        pid, user, rss_kb, args = cols[0], cols[1], int(cols[2]), cols[3].strip()
        if args.startswith("ps ") or args.startswith("sh ") or args.startswith("awk "):
            continue
        pkg_base = args.split(":")[0].split()[0]
        processes.append({
            "pid": int(pid),
            "user": user,
            "rss_mb": round(rss_kb / 1024, 1),
            "process": args,
            "package": pkg_base,
            "label": APP_FRIENDLY_NAMES.get(pkg_base, pkg_base),
            "killable": pkg_base in SWEEPABLE_APPS,
        })

    # 3. Parse dumpsys media_session for active session
    now_playing = {
        "active": False,
        "package": "",
        "app_name": "Idle",
        "title": "Nothing currently playing",
        "state": "Stopped",
        "position_sec": 0,
        "position_str": "00:00",
    }

    blocks = re.split(r"\n\s{4}(?=\S)", media_raw)
    for blk in blocks:
        if "active=true" not in blk:
            continue
        m_pkg = re.search(r"package=([\w\.]+)", blk)
        pkg = m_pkg.group(1) if m_pkg else ""
        m_state = re.search(r"state=PlaybackState\s*\{state=(\d+),\s*position=(-?\d+)", blk)
        state_code = int(m_state.group(1)) if m_state else 0
        pos_ms = int(m_state.group(2)) if m_state else 0
        m_meta = re.search(r"metadata:\s*size=\d+,\s*description=(.+)", blk)
        desc = m_meta.group(1).strip() if m_meta else ""
        # Clean up trailing ", null, null" from MediaDescription
        if desc:
            desc_parts = [p.strip() for p in desc.split(",") if p.strip() and p.strip() != "null"]
            # Deduplicate repeated segments
            cleaned = []
            for p in desc_parts:
                if p not in cleaned:
                    cleaned.append(p)
            desc = " — ".join(cleaned[:2]) if cleaned else desc

        state_map = {
            0: "Idle",
            1: "Stopped",
            2: "Paused",
            3: "Playing",
            6: "Buffering",
        }
        pos_sec = max(0, pos_ms // 1000)
        mins, secs = divmod(pos_sec, 60)
        hrs, mins = divmod(mins, 60)
        pos_str = f"{hrs}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"

        if state_code in (2, 3, 6) or desc:
            now_playing = {
                "active": state_code in (2, 3, 6),
                "package": pkg,
                "app_name": APP_FRIENDLY_NAMES.get(pkg, pkg or "Media Player"),
                "title": desc or "Media Playback Active",
                "state": state_map.get(state_code, "Active"),
                "position_sec": pos_sec,
                "position_str": pos_str,
            }
            if state_code == 3:
                break

    return {
        "connected": True,
        "tv_name": ENV.get("TV_NAME", "BRAVIA VU1"),
        "target": get_adb_target(),
        "ram": {
            "total_mb": total_mb,
            "available_mb": avail_mb,
            "used_mb": used_mb,
            "used_pct": round((used_mb / max(1, total_mb)) * 100),
            "swap_total_mb": swap_total_mb,
            "swap_used_mb": swap_used_mb,
            "swap_pct": round((swap_used_mb / max(1, swap_total_mb)) * 100),
        },
        "now_playing": now_playing,
        "processes": processes[:10],
    }


class RemoteRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        if not path.exists():
            self.send_error(404, "Not Found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._send_json(parse_status())
        elif parsed.path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif parsed.path == "/manifest.json":
            self._send_file(STATIC_DIR / "manifest.json", "application/manifest+json; charset=utf-8")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_body()

        if parsed.path == "/api/key":
            key = str(body.get("key", "")).upper()
            keycode = KEYCODE_MAP.get(key, key if key.startswith("KEYCODE_") else "")
            if not keycode:
                self._send_json({"ok": False, "error": f"Unknown key: {key}"}, 400)
                return
            if key in ("WAKEUP", "POWER"):
                send_wol()
            ok, out, err = run_adb(["shell", "input", "keyevent", keycode])
            self._send_json({"ok": ok, "key": key, "keycode": keycode, "error": err})

        elif parsed.path == "/api/text":
            text = str(body.get("text", ""))
            submit = bool(body.get("submit", False))
            if not text:
                self._send_json({"ok": False, "error": "Empty text"}, 400)
                return
            escaped = escape_adb_text(text)
            cmd_str = f'input text "{escaped}"'
            if submit:
                cmd_str += " && input keyevent KEYCODE_ENTER"
            ok, out, err = run_adb(["shell", cmd_str])
            self._send_json({"ok": ok, "error": err})

        elif parsed.path == "/api/app/launch":
            pkg = str(body.get("package", "")).strip()
            hdmi = body.get("hdmi")
            if hdmi in (1, 2, 3, 4, "1", "2", "3", "4"):
                act = f"com.spocky.projengmenu/.ui.guidedActions.activities.input.SourceHDMI{hdmi}Activity"
                ok, out, err = run_adb(["shell", "am", "start", "-n", act])
                self._send_json({"ok": ok, "launched": f"HDMI {hdmi}", "error": err})
                return
            if not pkg:
                self._send_json({"ok": False, "error": "Missing package"}, 400)
                return
            if pkg == "com.android.tv.settings":
                ok, out, err = run_adb(["shell", "am", "start", "-a", "android.settings.SETTINGS"])
            else:
                ok, out, err = run_adb([
                    "shell",
                    f"monkey -p {pkg} -c android.intent.category.LEANBACK_LAUNCHER 1 >/dev/null 2>&1 || "
                    f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1"
                ])
            self._send_json({"ok": ok, "package": pkg, "error": err})

        elif parsed.path == "/api/app/kill":
            pkg = str(body.get("package", "")).strip()
            if not pkg:
                self._send_json({"ok": False, "error": "Missing package"}, 400)
                return
            ok, out, err = run_adb(["shell", "am", "force-stop", pkg])
            self._send_json({"ok": ok, "killed": pkg, "error": err})

        elif parsed.path == "/api/ram/free":
            status_before = parse_status()
            before_mb = status_before.get("ram", {}).get("available_mb", 0)
            active_pkg = status_before.get("now_playing", {}).get("package", "")
            to_kill = [p for p in SWEEPABLE_APPS if p != active_pkg]
            kill_cmds = "; ".join(f"am force-stop {p}" for p in to_kill)
            run_adb(["shell", f"{kill_cmds}; pm trim-caches 999999999999999999"], timeout=8)
            status_after = parse_status()
            after_mb = status_after.get("ram", {}).get("available_mb", 0)
            self._send_json({
                "ok": True,
                "before_mb": before_mb,
                "after_mb": after_mb,
                "freed_mb": max(0, after_mb - before_mb),
                "status": status_after,
            })

        else:
            self._send_json({"ok": False, "error": "Not found"}, 404)


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def main():
    port = int(os.environ.get("REMOTE_PORT", sys.argv[1] if len(sys.argv) > 1 else 8765))
    lan_ip = get_lan_ip()
    server = ThreadingHTTPServer(("0.0.0.0", port), RemoteRequestHandler)
    print(f"============================================================")
    print(f"📺 Sony Bravia Web Remote & Control Center")
    print(f"   Target TV : {ENV.get('TV_NAME')} ({get_adb_target()})")
    print(f"   Mac URL   : http://localhost:{port}")
    print(f"   Phone URL : http://{lan_ip}:{port}  (Add to Home Screen)")
    print(f"============================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down remote server.")
        server.server_close()


if __name__ == "__main__":
    main()
