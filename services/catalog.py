"""Katalog produk dari database: baca tab "Database Kategori" & "Database Produk"
di Google Sheet via service account (pola auth sama dengan services/sheets.py).

Menyediakan untuk Web UI v2 (alur tanpa scrape Shopee):
- list_categories() -> [{"kategori": str, "sub": [str]}]
- list_products(kategori=None, sub=None, q=None) -> [produk ringkas]
- get_product(product_id) -> dict lengkap / None
- list_photos(product_id) -> [{"id","name","thumb","full"}] dari folder Drive produk

Cache in-memory TTL 5 menit agar dashboard tetap cepat.
"""
import re
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import C

TAB_KATEGORI = "Database Kategori"
TAB_PRODUK = "Database Produk"
CACHE_TTL = 300  # detik

_CACHE = {}


def _cached(key, loader, ttl=CACHE_TTL):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = loader()
    _CACHE[key] = (now, val)
    return val


def _sheets():
    if not C.GOOGLE_SA_FILE:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE belum diisi di .env")
    if not C.SHEET_ID:
        raise RuntimeError("SHEET_ID belum diisi di .env")
    creds = service_account.Credentials.from_service_account_file(
        C.GOOGLE_SA_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds)


def _drive():
    if not C.GOOGLE_SA_FILE:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE belum diisi di .env")
    creds = service_account.Credentials.from_service_account_file(
        C.GOOGLE_SA_FILE, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)


def _read_tab(tab, rng):
    svc = _sheets()
    res = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=C.SHEET_ID, range=f"'{tab}'!{rng}")
        .execute()
    )
    return res.get("values", [])


def _folder_id_from_link(link):
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", link or "")
    return m.group(1) if m else ""


def list_categories():
    """Kembalikan [{kategori, sub:[...]}] sesuai urutan di sheet."""

    def load():
        rows = _read_tab(TAB_KATEGORI, "A2:C500")
        cats, order = {}, []
        for r in rows:
            if len(r) < 2 or not r[0].strip():
                continue
            k, s = r[0].strip(), r[1].strip()
            if k not in cats:
                cats[k] = []
                order.append(k)
            if s and s not in cats[k]:
                cats[k].append(s)
        return [{"kategori": k, "sub": cats[k]} for k in order]

    return _cached("categories", load)


def _all_products():
    """Baca seluruh produk aktif sebagai dict lengkap (di-cache)."""

    def load():
        rows = _read_tab(TAB_PRODUK, "A2:S5000")
        out = []
        for r in rows:
            r = r + [""] * (19 - len(r))
            if not r[0].strip():
                continue
            if r[16].strip().lower() not in ("", "aktif"):
                continue
            out.append(
                {
                    "id": r[0].strip(),
                    "nama": r[1].strip(),
                    "kategori": r[2].strip(),
                    "sub": r[3].strip(),
                    "bulan_tahun": r[4].strip(),
                    "momen": r[5].strip(),
                    "harga": r[6].strip(),
                    "varian": r[7].strip(),
                    "ukuran": r[8].strip(),
                    "link_shopee": r[9].strip(),
                    "link_drive": r[10].strip(),
                    "foto_utama": r[11].strip(),
                    "rating": r[12].strip(),
                    "terjual": r[13].strip(),
                    "target": r[14].strip(),
                    "sumber": r[15].strip(),
                    "catatan": r[18].strip(),
                }
            )
        return out

    return _cached("products", load)


def _thumb_for(p):
    """URL thumbnail untuk grid dashboard: Foto Utama, fallback foto pertama folder Drive."""
    if p["foto_utama"]:
        return p["foto_utama"]
    fid = _folder_id_from_link(p["link_drive"])
    if not fid:
        return ""

    def load():
        try:
            svc = _drive()
            res = (
                svc.files()
                .list(
                    q=f"'{fid}' in parents and mimeType contains 'image/' and trashed=false",
                    fields="files(id)",
                    pageSize=1,
                    orderBy="name",
                )
                .execute()
            )
            files = res.get("files", [])
            if files:
                return f"https://drive.google.com/thumbnail?id={files[0]['id']}&sz=w400"
        except Exception:
            pass
        return ""

    return _cached(f"thumb:{p['id']}", load)


def list_products(kategori=None, sub=None, q=None):
    """Produk ringkas untuk dashboard. Filter opsional; q mencari di nama."""
    q = (q or "").strip().lower()
    out = []
    for p in _all_products():
        if kategori and p["kategori"] != kategori:
            continue
        if sub and p["sub"] != sub:
            continue
        if q and q not in p["nama"].lower():
            continue
        out.append(
            {
                "id": p["id"],
                "nama": p["nama"],
                "kategori": p["kategori"],
                "sub": p["sub"],
                "harga": p["harga"],
                "thumb": _thumb_for(p),
            }
        )
    return out


def get_product(product_id):
    for p in _all_products():
        if p["id"] == product_id:
            return dict(p)
    return None


def list_photos(product_id):
    """Semua foto produk dari folder Drive-nya (untuk tahap preview pilih foto)."""

    def load():
        p = get_product(product_id)
        if not p:
            return []
        fid = _folder_id_from_link(p["link_drive"])
        if not fid:
            # fallback: hanya foto utama
            return (
                [{"id": "utama", "name": "Foto utama",
                  "thumb": p["foto_utama"], "full": p["foto_utama"]}]
                if p["foto_utama"] else []
            )
        svc = _drive()
        res = (
            svc.files()
            .list(
                q=f"'{fid}' in parents and mimeType contains 'image/' and trashed=false",
                fields="files(id,name)",
                pageSize=50,
                orderBy="name",
            )
            .execute()
        )
        out = []
        for f in res.get("files", []):
            fid2 = f["id"]
            out.append(
                {
                    "id": fid2,
                    "name": f.get("name", fid2),
                    "thumb": f"https://drive.google.com/thumbnail?id={fid2}&sz=w800",
                    "full": f"https://drive.google.com/uc?export=download&id={fid2}",
                }
            )
        return out

    return _cached(f"photos:{product_id}", load)
