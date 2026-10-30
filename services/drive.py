"""Google Drive: cari/buat folder, upload file, set sharing publik."""
import os

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import C

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _service():
    if not C.GOOGLE_SA_FILE:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE belum diisi di .env")
    creds = service_account.Credentials.from_service_account_file(
        C.GOOGLE_SA_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def get_folder_id(svc=None):
    """Kembalikan ID folder tujuan (dari env, atau cari/buat by nama)."""
    svc = svc or _service()
    if C.DRIVE_FOLDER_ID:
        return C.DRIVE_FOLDER_ID
    q = (
        f"mimeType='application/vnd.google-apps.folder' "
        f"and name='{C.DRIVE_FOLDER_NAME}' and trashed=false"
    )
    res = svc.files().list(q=q, fields="files(id,name)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    folder = (
        svc.files()
        .create(
            body={"name": C.DRIVE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
        )
        .execute()
    )
    return folder["id"]


def upload_file(local_path, filename, folder_id=None):
    """Upload file, set sharing 'siapa saja yang memiliki link'.

    Kembalikan dict {id, webViewLink, downloadLink}.
    """
    svc = _service()
    folder_id = folder_id or get_folder_id(svc)
    media = MediaFileUpload(local_path, resumable=True)
    created = (
        svc.files()
        .create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id",
        )
        .execute()
    )
    file_id = created["id"]
    svc.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}
    ).execute()
    meta = svc.files().get(fileId=file_id, fields="id,webViewLink").execute()
    return {
        "id": file_id,
        "webViewLink": meta.get("webViewLink", ""),
        "downloadLink": f"https://drive.google.com/uc?export=download&id={file_id}",
    }
