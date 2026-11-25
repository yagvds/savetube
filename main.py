"""SaveTube - pengunduh video/gambar berbasis FastAPI + yt-dlp."""
import ipaddress, os, re, shutil, socket, tempfile, time
from collections import defaultdict
from urllib.parse import urlparse

import httpx
import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

MAX_FILESIZE = int(os.getenv("MAX_FILESIZE_MB", "500")) * 1024 * 1024
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")

app = FastAPI(title="SaveTube")
_hits: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request):
    ip = request.client.host if request.client else "x"
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < 60]
    if len(_hits[ip]) >= RATE_LIMIT:
        raise HTTPException(429, "Terlalu banyak permintaan. Coba lagi sebentar lagi.")
    _hits[ip].append(now)


def validate_url(url: str) -> str:
    """Hanya http(s) dan blokir alamat internal (perlindungan SSRF)."""
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HTTPException(400, "Tautan tidak valid.")
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(400, "Tautan tidak diizinkan.")
    except socket.gaierror:
        raise HTTPException(400, "Alamat tidak ditemukan.")
    return url.strip()


def is_direct_image(url: str) -> bool:
    return urlparse(url).path.lower().endswith(IMAGE_EXT)


class InfoReq(BaseModel):
    url: str


@app.post("/api/info")
def info(req: InfoReq, request: Request):
    rate_limit(request)
    url = validate_url(req.url)
    if is_direct_image(url):
        return {"title": os.path.basename(urlparse(url).path), "thumbnail": url,
                "duration": None, "kind": "image", "options": [{"id": "image", "label": "Gambar asli"}]}
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True, "skip_download": True}) as ydl:
            d = ydl.extract_info(url, download=False)
    except Exception:
        raise HTTPException(422, "Konten tidak bisa diambil. Pastikan tautan publik dan didukung.")
    heights = sorted({f["height"] for f in d.get("formats", []) if f.get("height")}, reverse=True)
    options = [{"id": f"v{h}", "label": f"Video MP4 {h}p"} for h in heights if h in (2160, 1440, 1080, 720, 480, 360)]
    if not options and d.get("formats"):
        options = [{"id": "vbest", "label": "Video kualitas terbaik"}]
    if any(f.get("acodec") not in (None, "none") for f in d.get("formats", [])):
        options.append({"id": "audio", "label": "Audio MP3"})
    if not options and d.get("thumbnail"):
        options = [{"id": "thumb", "label": "Gambar sampul"}]
    return {"title": d.get("title"), "thumbnail": d.get("thumbnail"), "duration": d.get("duration"),
            "kind": "video", "options": options}


def safe_name(s: str) -> str:
    return re.sub(r"[^\w\- ]+", "", s or "unduhan")[:80].strip() or "unduhan"


@app.get("/api/download")
def download(request: Request, url: str, option: str):
    rate_limit(request)
    url = validate_url(url)

    if option == "image" or (option == "thumb"):
        target = url
        if option == "thumb":
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                target = validate_url(ydl.extract_info(url, download=False)["thumbnail"])
        client = httpx.Client(follow_redirects=False, timeout=30)
        r = client.send(client.build_request("GET", target), stream=True)
        ext = os.path.splitext(urlparse(target).path)[1] or ".jpg"
        return StreamingResponse(r.iter_bytes(), media_type=r.headers.get("content-type", "image/jpeg"),
                                 headers={"Content-Disposition": f'attachment; filename="gambar{ext}"'},
                                 background=BackgroundTask(r.close))

    tmp = tempfile.mkdtemp(prefix="st_")
    opts = {"quiet": True, "noplaylist": True, "outtmpl": f"{tmp}/%(title).80s.%(ext)s",
            "max_filesize": MAX_FILESIZE}
    if option == "audio":
        opts.update(format="bestaudio/best", postprocessors=[
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}])
    else:
        h = option[1:]
        sel = f"[height<={h}]" if h.isdigit() else ""
        opts.update(format=f"bv*{sel}[ext=mp4]+ba[ext=m4a]/b{sel}/b", merge_output_format="mp4")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(422, "Gagal mengunduh. Ukuran terlalu besar atau konten tidak didukung.")
    files = os.listdir(tmp)
    if not files:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(422, "Berkas tidak ditemukan.")
    path = os.path.join(tmp, files[0])
    return FileResponse(path, filename=safe_name(os.path.splitext(files[0])[0]) + os.path.splitext(files[0])[1],
                        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True))


app.mount("/", StaticFiles(directory="static", html=True), name="static")
