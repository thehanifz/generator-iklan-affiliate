CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,                    -- iklan | affiliate
    product_url TEXT NOT NULL,
    supporting_urls TEXT DEFAULT '[]',     -- JSON array
    character_id TEXT,
    place_photo TEXT,                      -- path file lokal
    status TEXT NOT NULL DEFAULT 'antrean',-- antrean|diproses|proses story board|story board ready|gagal
    current_stage INTEGER DEFAULT 0,       -- index tahap 0..6
    progress INTEGER DEFAULT 0,            -- 0..100
    product_title TEXT,
    product_price TEXT,
    product_image TEXT,
    product_rating TEXT,
    product_meta TEXT DEFAULT '{}',     -- JSON: id, kategori, sub, momen, catatan, photos (alur database v2)
    supporting_data TEXT DEFAULT '[]',     -- JSON array
    storyboard_files TEXT DEFAULT '[]',    -- JSON array path lokal
    storyboard_urls TEXT DEFAULT '[]',     -- JSON array link Drive
    video_prompt TEXT,
    error TEXT,
    sheet_row INTEGER,                     -- nomor baris di Google Sheet
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS job_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    stage TEXT,
    message TEXT,
    level TEXT DEFAULT 'info'
);
CREATE INDEX IF NOT EXISTS idx_job_logs_job ON job_logs(job_id);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    photo_path TEXT,
    description TEXT,
    created_at TEXT
);
