"""Worker: memproses job 'antrean' tahap demi tahap, menulis log + progress.

Dijalankan sebagai thread di dalam app.py. Tanpa Celery/Redis (low maintenance).
Tahapan (sinkron dengan checklist UI):
  1. Memvalidasi input
  2. Mengambil informasi produk (v2: dari database katalog, tanpa scrape Shopee)
  3. Menganalisis foto karakter dan tempat
  4. Menyusun storyboard
  5. Membuat prompt video
  6. Menyiapkan hasil akhir (upload Drive + tulis Google Sheet)
"""
import json
import os
import threading
import time
import traceback
from datetime import date

import db
from config import C
from services import drive as drive_svc
from services import images as images_svc
from services import llm as llm_svc
from services import prompts as prompts_svc
from services import sheets as sheets_svc

STAGES = [
    "Memvalidasi input",
    "Mengambil informasi produk",
    "Menganalisis foto karakter dan tempat",
    "Menyusun storyboard",
    "Membuat prompt video",
    "Menyiapkan hasil akhir",
]


def _stage(conn, job_id, idx):
    name = STAGES[idx]
    pct = int((idx + 1) / len(STAGES) * 100)
    db.set_job(conn, job_id, current_stage=idx + 1, progress=pct)
    db.log(conn, job_id, f"Tahap {idx + 1}/{len(STAGES)}: {name}...", stage=name)
    conn.commit()


def _done_stage(conn, job_id, message):
    db.log(conn, job_id, message, stage="selesai")
    conn.commit()


def _fail(conn, job_id, message, sheet_row=None):
    db.set_job(conn, job_id, status="gagal", error=message)
    db.log(conn, job_id, f"GAGAL: {message}", level="error")
    conn.commit()
    if sheet_row:
        try:
            sheets_svc.update_row(sheet_row, Status="gagal", Error=message[:500])
        except Exception as e:
            db.log(conn, job_id, f"Tidak bisa update sheet: {e}", level="error")
            conn.commit()


def _get_character(conn, character_id):
    if not character_id:
        return {"name": "-", "description": "-"}
    row = conn.execute(
        "SELECT name, description FROM characters WHERE id=?", (character_id,)
    ).fetchone()
    if not row:
        return {"name": "-", "description": "-"}
    return {"name": row["name"], "description": row["description"] or "-"}


def process_job(job_id):
    conn = db.get_conn()
    try:
        job = db.row_to_dict(
            conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        )
        if not job or job["status"] != "antrean":
            return
        db.set_job(conn, job_id, status="diproses")
        db.log(conn, job_id, "Worker mengambil job.", stage="diproses")
        conn.commit()

        mode = job["mode"]
        sheet_row = None

        # ---- 1. validasi ----
        _stage(conn, job_id, 0)
        if not job["product_url"].startswith(("http://", "https://")):
            raise RuntimeError("Link produk utama tidak valid.")
        _done_stage(conn, job_id, "Validasi input berhasil.")

        # ---- 2. info produk ----
        _stage(conn, job_id, 1)
        try:
            meta = json.loads(job["product_meta"] or "{}")
        except Exception:
            meta = {}
        if meta.get("id"):
            # v2: data produk sudah lengkap dari database katalog (tanpa scrape)
            desc = meta.get("catatan") or " / ".join(
                x for x in (meta.get("kategori"), meta.get("sub")) if x
            )
            product = {
                "url": job["product_url"],
                "title": job["product_title"] or job["product_url"],
                "price": job["product_price"] or "",
                "image": job["product_image"] or "",
                "rating": job["product_rating"] or "",
                "description": desc,
            }
            supporting = [
                {
                    "title": s.get("nama", ""),
                    "price": s.get("harga", ""),
                    "url": s.get("link", ""),
                    "image": (s.get("photos") or [""])[0],
                }
                for s in db.jload(job["supporting_data"])
            ]
            db.set_job(
                conn, job_id,
                product_title=product["title"], product_price=product["price"],
                product_image=product["image"], supporting_data=db.jdump(supporting),
            )
            db.log(conn, job_id, f"Info produk dari database: {product['title'][:60]}")
        else:
            # legacy: job lama dari alur tempel-link (fetch Shopee best-effort)
            from services import shopee as shopee_svc
            try:
                product = shopee_svc.fetch_product(job["product_url"])
            except Exception:
                # pakai data preview yang sudah dikonfirmasi user
                product = {
                    "url": job["product_url"],
                    "title": job["product_title"] or job["product_url"],
                    "price": job["product_price"] or "",
                    "image": job["product_image"] or "",
                    "rating": "",
                    "description": "",
                }
                db.log(conn, job_id, "Fetch ulang gagal, memakai data preview.", level="warning")
            supporting = []
            for u in db.jload(job["supporting_urls"]):
                try:
                    supporting.append(shopee_svc.fetch_product(u))
                except Exception as e:
                    db.log(conn, job_id, f"Link penunjang dilewati: {e}", level="warning")
            db.set_job(
                conn, job_id,
                product_title=product["title"], product_price=product["price"],
                product_image=product["image"], supporting_data=db.jdump(supporting),
            )
        _done_stage(conn, job_id, f"Info produk didapat: {product['title'][:60]}")

        # insert ke sheet (status 'proses story board')
        try:
            char = _get_character(conn, job["character_id"])
            sup_links = " | ".join(
                s.get("url", "") for s in supporting if s.get("url")
            )
            sheet_row = sheets_svc.insert_row(
                product["title"], job["product_url"], mode,
                char["name"], date.today().isoformat(),
                allow_duplicate=True, supporting=sup_links,
            )
            db.set_job(conn, job_id, sheet_row=sheet_row)
            db.log(conn, job_id, f"Baris sheet dibuat (baris {sheet_row}), status 'proses story board'.")
        except Exception as e:
            db.log(conn, job_id, f"Sheet dilewati: {e}", level="warning")
        conn.commit()

        # ---- 3. analisis foto ----
        _stage(conn, job_id, 2)
        character = _get_character(conn, job["character_id"])
        place_note = "ada" if job["place_photo"] else "tidak ada (bebas sesuai konsep)"
        db.log(conn, job_id, f"Karakter: {character['name']}. Foto tempat: {place_note}.")
        _done_stage(conn, job_id, "Analisis foto selesai.")

        # ---- 4 & 5. storyboard + prompt via LLM ----
        _stage(conn, job_id, 3)
        tasks = prompts_svc.build_tasks(
            mode, llm_svc.chat,
            {"title": product["title"], "price": product["price"], "description": product["description"]},
            character,
        )
        db.log(conn, job_id, f"Konsep & shot list jadi ({len(tasks['storyboards'])} storyboard).")
        sb_files, sb_urls = [], []
        out_dir = os.path.join(C.OUTPUT_DIR, job_id)
        for sb in tasks["storyboards"]:
            fname = f"{product['title'][:40].strip()} - {sb['label']}.png"
            fname = "".join(c for c in fname if c.isalnum() or c in " -_.").strip() or "storyboard.png"
            local = os.path.join(out_dir, fname)
            db.log(conn, job_id, f"Generate {sb['label']} ({sb['grid']})...")
            conn.commit()
            images_svc.download(sb["prompt"], local, grid=sb["grid"])
            sb_files.append(local)
            db.log(conn, job_id, f"{sb['label']} selesai: {fname}")
            conn.commit()
        db.set_job(conn, job_id, storyboard_files=db.jdump(sb_files))
        _done_stage(conn, job_id, "Storyboard selesai.")

        _stage(conn, job_id, 4)
        # prompt video sudah dibuat di build_tasks (hemat 1 call)
        db.set_job(conn, job_id, video_prompt=tasks["video_prompt"])
        _done_stage(conn, job_id, "Prompt video selesai.")

        # ---- 6. hasil akhir ----
        _stage(conn, job_id, 5)
        for local in sb_files:
            try:
                up = drive_svc.upload_file(local, os.path.basename(local))
                sb_urls.append(up["webViewLink"])
                db.log(conn, job_id, f"Upload Drive: {os.path.basename(local)}")
            except Exception as e:
                db.log(conn, job_id, f"Upload Drive dilewati: {e}", level="warning")
        db.set_job(conn, job_id, storyboard_urls=db.jdump(sb_urls))
        if sheet_row:
            try:
                sheets_svc.update_row(
                    sheet_row,
                    Status="story board ready",
                    **{"Link storyboard": " | ".join(sb_urls),
                       "Prompt video": tasks["video_prompt"][:49000]},
                )
                db.log(conn, job_id, "Sheet diupdate: 'story board ready'.")
            except Exception as e:
                db.log(conn, job_id, f"Update sheet gagal: {e}", level="error")
        db.set_job(conn, job_id, status="story board ready", progress=100)
        db.log(conn, job_id, "Selesai. Storyboard + prompt video siap.", stage="selesai")
        conn.commit()
    except Exception as e:
        tb = traceback.format_exc(limit=3)
        try:
            row = conn.execute("SELECT sheet_row FROM jobs WHERE id=?", (job_id,)).fetchone()
            _fail(conn, job_id, f"{e}", sheet_row=row["sheet_row"] if row else None)
        except Exception:
            pass
        print(f"[worker] job {job_id} gagal: {tb}")
    finally:
        conn.close()


def _loop():
    while True:
        try:
            conn = db.get_conn()
            try:
                row = conn.execute(
                    "SELECT id FROM jobs WHERE status='antrean' ORDER BY created_at LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if row:
                # single worker thread -> tidak perlu klaim atomik
                process_job(row["id"])
        except Exception as e:
            print(f"[worker] loop error: {e}")
        time.sleep(C.POLL_SECONDS)


def start_worker():
    t = threading.Thread(target=_loop, daemon=True, name="job-worker")
    t.start()
    return t
