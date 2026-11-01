"""Helper SQLite: koneksi, init schema, CRUD kecil."""
import json
import os
import sqlite3
from datetime import datetime, timezone

from config import C

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "db", "schema.sql")


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    os.makedirs(os.path.dirname(C.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(C.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = f.read()
    conn = get_conn()
    try:
        conn.executescript(schema)
        # migrasi ringan: tambah kolom product_meta bila DB dibuat sebelum v2
        cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        if "product_meta" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN product_meta TEXT DEFAULT '{}'")
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def log(conn, job_id, message, stage=None, level="info"):
    conn.execute(
        "INSERT INTO job_logs (job_id, ts, stage, message, level) VALUES (?,?,?,?,?)",
        (job_id, _now(), stage, message, level),
    )


def set_job(conn, job_id, **fields):
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def jdump(obj):
    return json.dumps(obj, ensure_ascii=False)


def jload(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []
