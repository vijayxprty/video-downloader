# Video Downloader — free web tool (NOT live, NOT published)

Paste a link from YouTube, Instagram, Pinterest, or any other public web
video page. The app auto-detects the platform from the URL domain, shows
title / thumbnail / duration when available, and offers MP4 (video) and
MP3 (audio) downloads.

**Status: built and tested locally only. Nothing has been published,
deployed, or pushed to GitHub or Hugging Face. No Space was created.
No money was spent. No account credentials or tokens were used.**

## Rules this build follows

- Free always: no paid API, server, or domain. No Play Store / App Store.
  Web tool only.
- Private, login-only, removed/deleted, age-restricted, geo-blocked, or
  DRM-protected videos are NOT downloaded. You get a specific
  plain-language reason, not a generic error.
- No downloaded video is stored permanently. The backend writes to a
  temporary directory and deletes it after the file is sent to you.
- Never asks for, stores, or accepts user passwords, OTPs, or private
  account credentials.
- Respect platform terms: this is for your own videos, public-domain /
  Creative Commons videos, or videos you have permission for. Downloading
  someone else's copyrighted video without permission is not the intended
  use, and platform terms may prohibit it even for public links.

## Architecture split (for free hosting later)

```
Frontend (GitHub Pages)          Backend (Hugging Face Spaces, Docker)
index.html, app.js, style.css    backend/server.py, requirements.txt, Dockerfile
  HTML/CSS/JS only,               Python stdlib only + yt-dlp binary + ffmpeg
  no server code                  No database. No stored videos.
            │  single configurable URL  │
            └──── BACKEND_URL ──────────┘
```

- The frontend calls the backend through **one configurable
  `BACKEND_URL`**. It defaults to `http://localhost:8000` for local
  testing. In the page, open *Backend settings* and save your Space URL
  (saved in that browser only, via localStorage). No private URL is
  hard-coded into the page.
- GitHub Pages can only serve the frontend files. It cannot run yt-dlp
  or ffmpeg, so the backend must live separately — that is why the split
  exists.
- The backend is a plain Python HTTP server (standard library only).
  It shells out to `yt-dlp` for extraction and to `ffmpeg` (via yt-dlp)
  for MP3 conversion.

## Run locally (tested)

```bash
# 1. Backend — needs Python 3, yt-dlp, ffmpeg
pip install yt-dlp          # or: python3 -m venv .venv && .venv/bin/pip install yt-dlp
YTDLP_BIN=yt-dlp PORT=8000 HOST=127.0.0.1 python3 backend/server.py
# Health check: curl http://127.0.0.1:8000/health  -> {"ok": true, ...}

# 2. Frontend — any static server, in this folder:
python3 -m http.server 8080
# Open http://127.0.0.1:8080/ , paste a link, click "Check video".
# Backend URL in the page should be http://localhost:8000 (the default).
```

API (backend):
- `GET /health` → `{"ok": true}`
- `POST /api/info` with `{"url": "..."}` → platform, title, thumbnail,
  duration, uploader — or `{"ok": false, "code": "...", "message": "..."}`
  with a specific reason (see `classify_error` in `backend/server.py`).
- `GET /api/download?url=...&format=mp4|mp3` → file download, or a
  400 JSON error with a specific reason. Never a file for a blocked case.

## Deploy later (not done yet)

1. **Frontend → GitHub Pages:** push `index.html`, `app.js`, `style.css`
   to a public repo and enable Pages. That gives a free
   `username.github.io/<repo>/` address. No backend code runs there.
2. **Backend → Hugging Face Spaces (Docker, free CPU):** push the
   *contents* of `backend/` as the root of a new Docker Space repo
   (so `Dockerfile` is at the Space repo root). The image installs
   ffmpeg and yt-dlp, exposes port 7860, and runs `server.py`.
   In the frontend's Backend settings, save that Space URL.
3. No token, key, or password goes in the repo, the frontend, or the
   image. The backend needs no account of its own.

## Known limits — read before judging the tool

- **YouTube from a datacentre / cloud IP is often bot-checked.**
  In local testing here, public YouTube returned: “The platform blocked
  this request from this server (rate limit / bot check).” That is a
  real platform block, not a bug in the checker. It may work better from
  a home IP, and may still fail intermittently. No cookies or login
  credentials are used to bypass it, by design.
- **Free tiers sleep.** A Hugging Face free-CPU Space sleeps after
  inactivity and wakes on the next visit (slow first load). Render-style
  free services have the same problem, worse (15-minute sleep).
- **IP blocks and rate limits** from Instagram / Pinterest / YouTube
  can appear and disappear without any code change.
- **Large / long videos** take longer, use more CPU and bandwidth, and
  can time out on a free CPU (backend download timeout is 600 seconds
  by default, info timeout 60 seconds). There is no queue or progress
  bar beyond the browser's own download progress.
- **No login, no private content, no DRM.** Anything that needs an
  account, is private, removed, age-gated, geo-blocked, or DRM-protected
  will be refused with a specific reason.
- **Formats:** MP4 is best MP4 video + audio merged; MP3 is 192 kbps
  audio extracted with ffmpeg. Quality depends on what the platform
  serves for that public video.
- **CORS:** the backend currently allows any origin (`*`) so a GitHub
  Pages page can call it. That is fine for a public, no-auth tool, but
  it means anyone who knows the backend URL can use it — another reason
  to keep it free-tier and rate-limited in practice, not to put
  credentials behind it.

## Files

- `index.html`, `app.js`, `style.css` — static frontend (GitHub Pages)
- `backend/server.py` — backend (Python stdlib + yt-dlp + ffmpeg)
- `backend/requirements.txt` — `yt-dlp`
- `backend/Dockerfile` — Hugging Face Spaces Docker deployment
- `TEST-RESULTS.md` — exact local test results, link by link
