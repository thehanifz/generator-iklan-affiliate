# Generator Iklan & Affiliate

Web UI ringan (HTML + JS + CSS vanilla) + backend Python (Flask) + SQLite.
Alur: **Form → Preview Produk → Proses (progress + log) → Hasil + Google Sheet**.

Scope tahap awal: pembuatan **storyboard** dan **prompt video** saja.
Tidak ada render video (Flow), tidak ada upload otomatis (n8n), tidak ada cron.

## Struktur folder

```
generator-iklan-affiliate/
├── app.py               # Flask app + REST API + serve UI
├── worker.py            # Background worker (thread): proses job tahap demi tahap
├── config.py            # Baca konfigurasi dari .env
├── db.py                # Helper SQLite
├── db/schema.sql        # Skema: jobs, job_logs, characters
├── services/
│   ├── llm.py           # LLM OpenAI-compatible (OpenAI / 9Router)
│   ├── prompts.py       # Template konsep & prompt per mode (iklan / affiliate)
│   ├── images.py        # Generate storyboard (pollinations default / openai)
│   ├── shopee.py        # Fetch info produk dari link Shopee (best-effort)
│   ├── sheets.py        # Insert/update baris "Daftar video afiliet"
│   └── drive.py         # Upload storyboard ke folder "video afiliet"
├── templates/index.html # UI (4 tahap)
├── static/{style.css,app.js}
├── data/                # DB + upload + output (dibuat otomatis, jangan di-commit)
├── requirements.txt
├── .env.example
└── README.md
```

## Cara jalan (5 menit)

```bash
cd generator-iklan-affiliate
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# isi .env (minimal: LLM_API_KEY; Google opsional — lihat bawah)
python app.py
# buka http://localhost:5000/
```

Tanpa API key pun aplikasi jalan: job akan gagal di tahap LLM dengan pesan jelas
di log (bukan crash), dan bisa di-`Coba Lagi` setelah key diisi.

## Konfigurasi penting (.env)

| Key | Fungsi |
|---|---|
| `APP_TOKEN` | Token sederhana untuk buka UI/API (header `X-Token` atau `?token=`). Kosong = tanpa auth |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | LLM OpenAI-compatible. Contoh 9Router: `http://IP-SERVER:20128/v1` |
| `IMAGE_PROVIDER` | `pollinations` (gratis, tanpa key) atau `openai` |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path JSON service account untuk Sheets & Drive |
| `SHEET_ID` | ID spreadsheet "Daftar video afiliet" |
| `DRIVE_FOLDER_ID` / `DRIVE_FOLDER_NAME` | Folder tujuan storyboard |

**Google setup singkat:** buat service account di Google Cloud Console → aktifkan
Sheets API + Drive API → buat key JSON → share spreadsheet & folder Drive ke email
service account tersebut (sebagai Editor).

## API (ringkas)

| Method | Endpoint | Keterangan |
|---|---|---|
| POST | `/api/preview` `{url}` | Info produk (judul, harga, foto) |
| POST | `/api/jobs` | Buat job (multipart form) → `{job_id}` |
| GET | `/api/jobs/:id` | Status, tahap, progress |
| GET | `/api/jobs/:id/logs?since=` | Log incremental (polling tiap 2 dtk) |
| GET | `/api/jobs/:id/result` | URL storyboard + prompt video |
| POST | `/api/jobs/:id/retry` | Ulangi job gagal |
| GET/POST/DELETE | `/api/characters` | CRUD karakter |

## Status job & Sheet

`antrean` → `diproses` → `proses story board` → `story board ready` / `gagal`.
Sheet ditulis saat job dibuat (`proses story board`) dan saat selesai
(`story board ready` + link storyboard + prompt) atau gagal (`gagal` + error).

## Catatan jujur / batasan

- Fetch Shopee bersifat best-effort (Shopee sering memblokir akses otomatis).
  Jika gagal, UI menawarkan isi manual — bukan data karangan.
- Ketepatan jumlah panel storyboard tergantung provider image generation.
- Mode `iklan`: 1 konsep, storyboard 10 panel (5×2), 1 prompt. Mode `affiliate`:
  2 segmen @8 detik, storyboard 2×2 per segmen, prompt base + extend + voiceover.
