"""Google Sheets: insert & update baris "Daftar video afiliet".

Auth: service account JSON (GOOGLE_SERVICE_ACCOUNT_FILE).
Spreadsheet & tab "Daftar video afiliet" harus di-share ke email service account.
"""
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import C

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = [
    "Produk", "Link Shopee", "Link Penunjang", "Mode", "Karakter", "Tanggal",
    "Durasi", "Judul + tag (≤150)", "Link video Drive", "Link storyboard",
    "Prompt video", "Status", "Waktu upload", "Error", "Caption",
]
COL_STATUS = HEADERS.index("Status") + 1  # 1-based untuk notasi A1


def _service():
    if not C.GOOGLE_SA_FILE:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE belum diisi di .env")
    if not C.SHEET_ID:
        raise RuntimeError("SHEET_ID belum diisi di .env")
    creds = service_account.Credentials.from_service_account_file(
        C.GOOGLE_SA_FILE, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def _col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def find_row_by_link(svc, product_url):
    """Cari nomor baris berdasarkan Link Shopee (kolom B). Kembalikan int/None."""
    res = (
        svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=C.SHEET_ID,
            range=f"{C.SHEET_TAB}!B:B",
            fields="values",
        )
        .execute()
    )
    for i, row in enumerate(res.get("values", []), start=1):
        if row and row[0].strip() == product_url.strip():
            return i
    return None


def insert_row(product_title, product_url, mode, character_name, date_str,
               allow_duplicate=False, supporting=""):
    """Tambah baris baru, status 'proses story board'. Kembalikan nomor baris.

    allow_duplicate=True: lewati cek duplikat (untuk alur database v2, tiap job
    = 1 video baru walau produknya sama). supporting: teks "Link Penunjang".
    """
    svc = _service()
    if not allow_duplicate and find_row_by_link(svc, product_url):
        raise RuntimeError("Link produk ini sudah ada di sheet (duplikat).")
    row = [""] * len(HEADERS)
    row[0] = product_title
    row[1] = product_url
    row[2] = supporting
    row[3] = mode
    row[4] = character_name or ""
    row[5] = date_str
    row[11] = "proses story board"
    res = (
        svc.spreadsheets()
        .values()
        .append(
            spreadsheetId=C.SHEET_ID,
            range=f"{C.SHEET_TAB}!A:{_col_letter(len(HEADERS))}",
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        )
        .execute()
    )
    updated = res.get("updates", {}).get("updatedRange", "")
    import re

    m = re.search(r"!A(\d+):", updated)
    return int(m.group(1)) if m else None


def update_row(row_num, **fields):
    """Update sel per nama kolom, mis. update_row(5, Status='story board ready')."""
    if not row_num:
        return
    svc = _service()
    data = []
    for name, value in fields.items():
        if name not in HEADERS:
            raise RuntimeError(f"Kolom tidak dikenal: {name}")
        col = _col_letter(HEADERS.index(name) + 1)
        data.append(
            {"range": f"{C.SHEET_TAB}!{col}{row_num}", "values": [[value]]}
        )
    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=C.SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
