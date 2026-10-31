// Frontend for the video downloader. Static only — no server code here.
// The backend is a single configurable URL, never a hard-coded private URL.
// Default is local development; the user can change it in Backend settings
// and it is saved in this browser only (localStorage).
const DEFAULT_BACKEND = "http://localhost:8000";

function getBackend() {
  return (localStorage.getItem("vd-backend") || window.BACKEND_URL || DEFAULT_BACKEND)
    .replace(/\/$/, "");
}

const $ = (id) => document.getElementById(id);
const urlEl = $("url"), checkBtn = $("checkBtn"), platformEl = $("platform"),
      resultEl = $("result"), errorEl = $("error"), thumbEl = $("thumb"),
      titleEl = $("title"), metaEl = $("meta"), mp4Btn = $("mp4Btn"), mp3Btn = $("mp3Btn"),
      backendEl = $("backend");

backendEl.value = getBackend();

function detectPlatform(url) {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    if (host === "youtube.com" || host === "youtu.be" || host.endsWith(".youtube.com")) return "YouTube";
    if (host === "instagram.com" || host.endsWith(".instagram.com")) return "Instagram";
    if (host === "pinterest.com" || host === "pin.it" || host.endsWith(".pinterest.com")) return "Pinterest";
    return "Web video";
  } catch { return "Web video"; }
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  resultEl.hidden = true;
}

$("saveBackend").addEventListener("click", () => {
  const v = backendEl.value.trim().replace(/\/$/, "");
  if (!/^https?:\/\//.test(v)) { showError("Backend URL must start with http:// or https://"); return; }
  localStorage.setItem("vd-backend", v);
  errorEl.hidden = true;
  alert("Backend URL saved: " + v);
});

urlEl.addEventListener("input", () => {
  const u = urlEl.value.trim();
  if (u) { platformEl.textContent = "Detected: " + detectPlatform(u); platformEl.hidden = false; }
  else { platformEl.hidden = true; }
});

checkBtn.addEventListener("click", async () => {
  const url = urlEl.value.trim();
  if (!url) { showError("Please paste a video link first."); return; }
  errorEl.hidden = true; resultEl.hidden = true;
  checkBtn.disabled = true; checkBtn.textContent = "Checking…";
  try {
    const res = await fetch(getBackend() + "/api/info", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url}),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) { showError(data.message || "Could not read this video."); return; }
    titleEl.textContent = data.title || "Untitled video";
    const dur = data.duration_string || (data.duration ? Math.round(data.duration) + " sec" : "");
    metaEl.textContent = [data.platform, data.uploader, dur].filter(Boolean).join(" · ");
    if (data.thumbnail) { thumbEl.src = data.thumbnail; thumbEl.hidden = false; }
    else { thumbEl.hidden = true; }
    const enc = encodeURIComponent(url);
    mp4Btn.href = getBackend() + "/api/download?url=" + enc + "&format=mp4";
    mp3Btn.href = getBackend() + "/api/download?url=" + enc + "&format=mp3";
    resultEl.hidden = false;
  } catch (e) {
    showError("Could not reach the backend at " + getBackend() + ". Is it running? (Locally: python backend/server.py)");
  } finally {
    checkBtn.disabled = false; checkBtn.textContent = "Check video";
  }
});
