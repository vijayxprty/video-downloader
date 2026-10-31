#!/usr/bin/env python3
"""Video downloader backend — free, no accounts, no stored videos.

Runs with only the Python standard library + the yt-dlp binary + ffmpeg.
No user passwords, OTPs, or private credentials are ever requested, stored,
or accepted. Downloaded files live only in a temporary directory and are
deleted after the response is sent.

Endpoints:
  GET  /health            -> {"ok": true}
  POST /api/info          -> {"url": "..."}  -> title/thumbnail/duration/platform
  GET  /api/download?url=...&format=mp4|mp3  -> file download (streamed)

Environment:
  PORT       (default 8000; Hugging Face Spaces Docker uses 7860)
  HOST       (default 127.0.0.1; set 0.0.0.0 in Docker)
  YTDLP_BIN  (default "yt-dlp" from PATH)
  INFO_TIMEOUT, DOWNLOAD_TIMEOUT (seconds)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

YTDLP = os.environ.get("YTDLP_BIN", "yt-dlp")
INFO_TIMEOUT = int(os.environ.get("INFO_TIMEOUT", "60"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "600"))

PLATFORMS = [
    ("youtube.com", "YouTube"), ("youtu.be", "YouTube"),
    ("instagram.com", "Instagram"),
    ("pinterest.com", "Pinterest"), ("pin.it", "Pinterest"),
    ("tiktok.com", "TikTok"),
    ("facebook.com", "Facebook"), ("fb.watch", "Facebook"),
    ("x.com", "X (Twitter)"), ("twitter.com", "X (Twitter)"),
    ("vimeo.com", "Vimeo"),
    ("dailymotion.com", "Dailymotion"),
    ("twitch.tv", "Twitch"),
    ("reddit.com", "Reddit"),
]


def detect_platform(url):
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return "Web video"
    host = host[4:] if host.startswith("www.") else host
    for domain, name in PLATFORMS:
        if host == domain or host.endswith("." + domain):
            return name
    return "Web video"


def classify_error(text):
    """Map yt-dlp output to a specific, plain-language reason. Never generic."""
    t = (text or "").lower()
    if "drm" in t or "digital rights management" in t:
        return ("drm", "This video is DRM-protected streaming content and cannot be downloaded.")
    if "private video" in t or "this video is private" in t or "video is private" in t:
        return ("private", "This video is private. Only the owner or approved viewers can watch it, so it cannot be downloaded.")
    # Bot checks come BEFORE login: "Sign in to confirm you're not a bot" is
    # a platform block from this server's IP, not a login-only video.
    if ("not a bot" in t or "not a robot" in t or "confirm you" in t
            or "rate limit" in t or "too many requests" in t or "429" in t
            or "bot" in t or "ip" in t and "blocked" in t):
        return ("platform_blocked", "The platform blocked this request from this server (rate limit / bot check). Try again later, or try a different public link.")
    if ("login" in t or "log in" in t or "sign in" in t or "requires authentication" in t
            or "cookies" in t or "only available to" in t or "account" in t and "required" in t):
        return ("login_required", "This video needs a signed-in account to watch. Login-only videos are not downloaded here.")
    if ("removed" in t or "deleted" in t or "has been removed" in t or "no longer available" in t
            or "not found" in t or "404" in t or "video unavailable" in t or "is unavailable" in t
            or "unavailable" in t):
        return ("removed", "This video has been removed, deleted, or the link is no longer available.")
    if "age" in t and ("restrict" in t or "confirm" in t or "adult" in t):
        return ("age_restricted", "This video is age-restricted and needs a signed-in adult account, so it cannot be downloaded here.")
    if "geo" in t or "not available in your country" in t or "blocked in your country" in t or "region" in t:
        return ("geo_blocked", "This video is not available in this region (geo-blocked).")
    if "live stream" in t or "premiere" in t or "upcoming" in t:
        return ("not_ready", "This is a live stream or upcoming premiere, not a finished video yet, so it cannot be downloaded.")
    if ("rate limit" in t or "too many requests" in t or "429" in t
            or "bot" in t or "sign in to confirm" in t or "confirm you are not a robot" in t
            or "ip" in t and "blocked" in t):
        return ("platform_blocked", "The platform blocked this request from this server (rate limit / bot check). Try again later, or try a different public link.")
    if "unsupported url" in t or "no video formats" in t or "no suitable" in t:
        return ("unsupported", "This link does not point to a downloadable public video, or this site is not supported.")
    if "timed out" in t or "timeout" in t or "connection" in t or "network" in t:
        return ("network", "The download timed out or the network failed. Try again, or try a smaller / shorter video.")
    # Fall back to a trimmed, specific detail instead of a generic error.
    # Drop yt-dlp's "null" JSON stdout line, which is not a useful detail.
    cleaned = "\n".join(ln for ln in (text or "").splitlines() if ln.strip() != "null")
    detail = re.sub(r"\s+", " ", cleaned.strip())[-240:]
    return ("failed", f"Could not download this video. {detail}" if detail else "Could not download this video.")


def valid_public_url(url):
    if not isinstance(url, str) or not (8 <= len(url) <= 2048):
        return False
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or not p.netloc:
        return False
    host = p.hostname or ""
    if host in ("localhost",) or host.startswith("127.") or host.startswith("10.") \
            or host.startswith("192.168.") or host.startswith("172.16.") \
            or host.startswith("172.17.") or host.startswith("172.18."):
        return False
    return True


def run_ytdlp(args, timeout):
    try:
        proc = subprocess.run(
            [YTDLP] + args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, "yt-dlp is not installed on this server."
    except subprocess.TimeoutExpired:
        return None, "Timed out."
    return proc, (proc.stdout or "") + "\n" + (proc.stderr or "")


def get_info(url):
    proc, out = run_ytdlp(
        ["--dump-single-json", "--no-playlist", "--no-warnings", url],
        INFO_TIMEOUT)
    if proc is None or proc.returncode != 0:
        code, message = classify_error(out)
        return None, code, message
    try:
        data = json.loads(proc.stdout)
    except Exception:
        return None, "failed", "Could not read the video details from this link."
    return {
        "platform": detect_platform(url),
        "url": url,
        "title": data.get("title") or "Untitled video",
        "thumbnail": data.get("thumbnail"),
        "duration": data.get("duration"),
        "duration_string": data.get("duration_string"),
        "uploader": data.get("uploader") or data.get("channel"),
        "webpage_url": data.get("webpage_url") or url,
    }, None, None


def download_file(url, fmt, tmpdir):
    if fmt == "mp3":
        args = ["--no-playlist", "--no-warnings", "-x", "--audio-format", "mp3",
                "--audio-quality", "192K", "-o", os.path.join(tmpdir, "out.%(ext)s"), url]
        ext, content_type = "mp3", "audio/mpeg"
    else:
        args = ["--no-playlist", "--no-warnings",
                "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
                "--merge-output-format", "mp4",
                "-o", os.path.join(tmpdir, "out.%(ext)s"), url]
        ext, content_type = "mp4", "video/mp4"
    proc, out = run_ytdlp(args, DOWNLOAD_TIMEOUT)
    if proc is None or proc.returncode != 0:
        code, message = classify_error(out)
        return None, code, message, content_type
    candidates = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
    candidates = [f for f in candidates if os.path.isfile(f)]
    if not candidates:
        return None, "failed", "Download finished but no file was produced.", content_type
    path = max(candidates, key=os.path.getsize)
    return path, None, None, content_type


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), args[0] % args[1:]))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/health"):
            return self._json(200, {"ok": True, "service": "video-downloader"})
        if parsed.path == "/api/download":
            qs = urllib.parse.parse_qs(parsed.query)
            url = (qs.get("url") or [""])[0]
            fmt = (qs.get("format") or ["mp4"])[0].lower()
            if fmt not in ("mp4", "mp3"):
                return self._json(400, {"ok": False, "code": "bad_format",
                                        "message": "Format must be mp4 or mp3."})
            if not valid_public_url(url):
                return self._json(400, {"ok": False, "code": "bad_url",
                                        "message": "Please paste a valid http(s) video link."})
            tmpdir = tempfile.mkdtemp(prefix="vd-")
            try:
                path, code, message, content_type = download_file(url, fmt, tmpdir)
                if path is None:
                    return self._json(400, {"ok": False, "code": code, "message": message})
                size = os.path.getsize(path)
                filename = f"video.{fmt}"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(size))
                self._cors()
                self.end_headers()
                with open(path, "rb") as fh:
                    shutil.copyfileobj(fh, self.wfile, length=1024 * 256)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
            return
        return self._json(404, {"ok": False, "code": "not_found", "message": "Unknown endpoint."})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/info":
            return self._json(404, {"ok": False, "code": "not_found", "message": "Unknown endpoint."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json(400, {"ok": False, "code": "bad_json", "message": "Invalid request."})
        url = payload.get("url", "")
        if not valid_public_url(url):
            return self._json(400, {"ok": False, "code": "bad_url",
                                    "message": "Please paste a valid http(s) video link."})
        info, code, message = get_info(url)
        if info is None:
            return self._json(400, {"ok": False, "code": code, "message": message})
        return self._json(200, {"ok": True, **info})


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    if shutil.which(YTDLP) is None and not os.path.exists(YTDLP):
        print(f"WARNING: yt-dlp binary not found: {YTDLP}", file=sys.stderr)
    print(f"video-downloader backend on http://{host}:{port} (yt-dlp: {YTDLP})", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
