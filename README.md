# SaveTube

Situs pengunduh video/gambar (gaya SaveFrom.net). Backend FastAPI + yt-dlp, frontend HTML polos.

## Menjalankan
```bash
sudo apt install ffmpeg          # wajib untuk gabung video+audio dan MP3
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```
Buka http://localhost:8000

## Pengaturan (env)
- `MAX_FILESIZE_MB` (default 500) - batas ukuran unduhan
- `RATE_LIMIT_PER_MIN` (default 10) - batas permintaan per IP

## Penting
- Perbarui yt-dlp rutin (`pip install -U yt-dlp`); platform sering mengubah sistemnya.
- Letakkan di belakang Nginx/Caddy dengan HTTPS; pasang rate limit tambahan di sana.
- Unduh hanya konten milik sendiri, berlisensi terbuka, atau yang diizinkan pemiliknya. Mengunduh konten berhak cipta dapat melanggar ketentuan platform dan hukum. Siapkan halaman Syarat Penggunaan dan kontak penghapusan (DMCA) sebelum dipublikasikan.
