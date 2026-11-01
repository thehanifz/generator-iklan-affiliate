"""Konfigurasi aplikasi dari environment variable (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _get(name, default=""):
    return os.getenv(name, default)


class C:
    APP_TOKEN = _get("APP_TOKEN", "")
    DB_PATH = _get("DB_PATH", "data/app.db")
    UPLOAD_DIR = _get("UPLOAD_DIR", "data/uploads")
    OUTPUT_DIR = _get("OUTPUT_DIR", "data/outputs")
    PORT = int(_get("PORT", "5000"))
    HOST = _get("HOST", "0.0.0.0")
    POLL_SECONDS = int(_get("WORKER_POLL_SECONDS", "5"))

    SHOPEE_USER = _get("SHOPEE_USER", "") or _get("shopee_user", "")
    SHOPEE_PASS = _get("SHOPEE_PASS", "") or _get("shopee_pass", "")

    GOOGLE_SA_FILE = _get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    SHEET_ID = _get("SHEET_ID", "")
    SHEET_TAB = _get("SHEET_TAB", "Sheet1")
    DRIVE_FOLDER_ID = _get("DRIVE_FOLDER_ID", "")
    DRIVE_FOLDER_NAME = _get("DRIVE_FOLDER_NAME", "video afiliet")

    LLM_BASE_URL = _get("LLM_BASE_URL", "https://hermuse.thehanifz.my.id/v1")
    LLM_API_KEY = _get("LLM_API_KEY", "")
    LLM_MODEL = _get("LLM_MODEL", "combo-ag")

    IMAGE_PROVIDER = _get("IMAGE_PROVIDER", "openai")
    IMAGE_MODEL = _get("IMAGE_MODEL", "ag/gemini-3.1-flash-image")
    IMAGE_BASE_URL = _get("IMAGE_BASE_URL", "")
    IMAGE_API_KEY = _get("IMAGE_API_KEY", "")
