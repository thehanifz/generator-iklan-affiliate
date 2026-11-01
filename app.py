"""Generator Iklan & Affiliate — Flask API + UI vanilla.

Jalankan:  python app.py   (atau: flask --app app run)
UI:        http://localhost:5000/

v2: produk diambil dari database katalog (Google Sheet "Database Produk" +
foto Drive), bukan scrape Shopee. Alur: Dashboard (pilih ≤5 produk) ->
Preview foto -> Proses -> Hasil.
"""
import json
import os
import uuid
from datetime import date
from functools import wraps

from flask import Flask, jsonify, render_template, request, send_from_directory

import db
from config import C
from services import catalog
from worker import start_worker

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB


# ---------- auth sederhana ----------
def require_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if C.APP_TOKEN:
            got = request.headers.get("X-Token") or request.args.get("token", "")
            if got != C.APP_TOKEN:
                return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapper


# ---------- halaman ----------
@app.route("/")
@require_token
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"ok": True})


# ---------- katalog produk (database, tanpa scrape Shopee) ----------
@app.route("/api/catalog/categories")
@require_token
def api_catalog_categories():
    try:
        return jsonify({"ok": True, "categories": catalog.list_categories()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@app.route("/api/catalog/products")
@require_token
def api_catalog_products():
    try:
        return jsonify({
            "ok": True,
            "products": catalog.list_products(
                kategori=request.args.get("kategori") or None,
                sub=request.args.get("sub") or None,
                q=request.args.get("q") or None,
            ),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@app.route("/api/drive-image/<file_id>")
def api_drive_image(file_id):
    """Proxy image dari Google Drive via service account agar bebas CORS / rate limit."""
    import io
    from flask import send_file, Response
    download = request.args.get("download")
    try:
        svc = catalog._drive()
        req = svc.files().get_media(fileId=file_id)
        content = req.execute()
        as_attachment = bool(download)
        filename = f"{file_id}.jpg"
        return send_file(
            io.BytesIO(content),
            mimetype="image/jpeg",
            as_attachment=as_attachment,
            download_name=filename if as_attachment else None
        )
    except Exception as e:
        return Response(f"Error fetching image: {e}", status=502)


@app.route("/api/catalog/products/<pid>/photos")
@require_token
def api_catalog_photos(pid):
    try:
        photos = catalog.list_photos(pid)
        if not photos and not catalog.get_product(pid):
            return jsonify({"ok": False, "error": "produk tidak ditemukan"}), 404
        return jsonify({"ok": True, "photos": photos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


# ---------- jobs ----------
def _save_upload(file_storage, subdir):
    if not file_storage or not file_storage.filename:
        return ""
    dest_dir = os.path.join(C.UPLOAD_DIR, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = f"{uuid.uuid4().hex}_{file_storage.filename}"
    path = os.path.join(dest_dir, name)
    file_storage.save(path)
    return path


@app.route("/api/jobs", methods=["POST"])
@require_token
def api_create_job():
    mode = request.form.get("mode", "affiliate")
    if mode not in ("iklan", "affiliate"):
        return jsonify({"error": "mode harus iklan/affiliate"}), 400

    # Produk dari database katalog: [{id, utama, photos:[url,...]}], maks 5
    try:
        chosen = json.loads(request.form.get("products_json") or "[]")
    except Exception:
        return jsonify({"error": "data produk tidak valid"}), 400
    if not isinstance(chosen, list) or not (1 <= len(chosen) <= 5):
        return jsonify({"error": "pilih 1–5 produk dari dashboard"}), 400

    items = []
    for entry in chosen:
        pid = (entry.get("id") or "").strip()
        photos = [u for u in (entry.get("photos") or [])
                  if isinstance(u, str) and u.startswith("http")]
        if not pid:
            return jsonify({"error": "ID produk kosong"}), 400
        if not photos:
            return jsonify({"error": f"produk {pid}: pilih minimal 1 foto"}), 400
        p = catalog.get_product(pid)
        if not p:
            return jsonify({"error": f"produk {pid} tidak ditemukan di database"}), 404
        items.append({"db": p, "photos": photos, "utama": bool(entry.get("utama"))})

    mains = [it for it in items if it["utama"]]
    if len(mains) != 1:
        # default: produk pertama = produk utama
        for it in items:
            it["utama"] = False
        items[0]["utama"] = True
    main = next(it for it in items if it["utama"])
    supporting = [it for it in items if not it["utama"]]
    mdb = main["db"]

    character_id = request.form.get("character_id") or None
    place_photo = _save_upload(request.files.get("place_photo"), "places")

    sup_data = [
        {"id": it["db"]["id"], "nama": it["db"]["nama"], "harga": it["db"]["harga"],
         "link": it["db"]["link_shopee"], "photos": it["photos"]}
        for it in supporting
    ]
    meta = {
        "id": mdb["id"], "kategori": mdb["kategori"], "sub": mdb["sub"],
        "momen": mdb["momen"], "catatan": mdb["catatan"], "photos": main["photos"],
    }

    job_id = uuid.uuid4().hex[:12]
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO jobs (id, mode, product_url, supporting_urls, character_id,
               place_photo, status, product_title, product_price, product_image,
               product_meta, supporting_data, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id, mode, mdb["link_shopee"],
                db.jdump([it["db"]["link_shopee"] for it in supporting]),
                character_id, place_photo, "antrean",
                mdb["nama"], mdb["harga"], main["photos"][0],
                db.jdump(meta), db.jdump(sup_data),
                db._now(), db._now(),
            ),
        )
        db.log(conn, job_id, "Job dibuat, menunggu diproses worker.", stage="antrean")
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/jobs/<job_id>")
@require_token
def api_get_job(job_id):
    conn = db.get_conn()
    try:
        job = db.row_to_dict(
            conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        )
    finally:
        conn.close()
    if not job:
        return jsonify({"error": "job tidak ditemukan"}), 404
    return jsonify({"ok": True, "job": job})


@app.route("/api/jobs/<job_id>/logs")
@require_token
def api_get_logs(job_id):
    since = request.args.get("since", "0")
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, ts, stage, message, level FROM job_logs "
            "WHERE job_id=? AND id>? ORDER BY id ASC",
            (job_id, since),
        ).fetchall()
    finally:
        conn.close()
    return jsonify({"ok": True, "logs": [dict(r) for r in rows]})


@app.route("/api/jobs/<job_id>/result")
@require_token
def api_get_result(job_id):
    conn = db.get_conn()
    try:
        job = db.row_to_dict(
            conn.execute(
                "SELECT status, storyboard_urls, video_prompt, error FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
        )
    finally:
        conn.close()
    if not job:
        return jsonify({"error": "job tidak ditemukan"}), 404
    if job["status"] != "story board ready":
        return jsonify({"ok": False, "status": job["status"], "error": job["error"]}), 409
    return jsonify(
        {
            "ok": True,
            "storyboard_urls": db.jload(job["storyboard_urls"]),
            "video_prompt": job["video_prompt"],
        }
    )


@app.route("/api/jobs/<job_id>/retry", methods=["POST"])
@require_token
def api_retry(job_id):
    conn = db.get_conn()
    try:
        cur = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not cur:
            return jsonify({"error": "job tidak ditemukan"}), 404
        if cur["status"] != "gagal":
            return jsonify({"error": "hanya job gagal yang bisa diulang"}), 409
        db.set_job(conn, job_id, status="antrean", error="", current_stage=0, progress=0)
        db.log(conn, job_id, "Job diulang oleh pengguna.", stage="antrean")
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


# ---------- karakter ----------
@app.route("/api/characters")
@require_token
def api_list_characters():
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, photo_path, description FROM characters ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    chars = [dict(r) for r in rows]
    for c in chars:
        c["photo_url"] = f"/uploads/characters/{os.path.basename(c['photo_path'])}" if c["photo_path"] else ""
    return jsonify({"ok": True, "characters": chars})


@app.route("/api/characters", methods=["POST"])
@require_token
def api_add_character():
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "nama karakter wajib diisi"}), 400
    photo = _save_upload(request.files.get("photo"), "characters")
    desc = request.form.get("description") or ""
    cid = uuid.uuid4().hex[:8]
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO characters (id, name, photo_path, description, created_at) VALUES (?,?,?,?,?)",
            (cid, name, photo, desc, db._now()),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "id": cid})


@app.route("/api/characters/<cid>", methods=["DELETE"])
@require_token
def api_del_character(cid):
    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM characters WHERE id=?", (cid,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/uploads/characters/<path:fname>")
@require_token
def serve_char_photo(fname):
    return send_from_directory(os.path.join(C.UPLOAD_DIR, "characters"), fname)


@app.route("/uploads/products/<path:fname>")
@require_token
def serve_product_photo(fname):
    return send_from_directory(os.path.join(C.UPLOAD_DIR, "products"), fname)


@app.route("/outputs/<path:fname>")
@require_token
def serve_output(fname):
    return send_from_directory(C.OUTPUT_DIR, fname)


if __name__ == "__main__":
    db.init_db()
    start_worker()
    app.run(host=C.HOST, port=C.PORT, debug=False)
