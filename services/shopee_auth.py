"""Login Shopee via QR Code menggunakan Headless Chrome (Playwright).

Alur:
1. generate_qr():
   - Menjalankan headless Chrome via Playwright.
   - Membuka https://shopee.co.id/buyer/login/qr dengan sidik jari peramban nyata.
   - Menangkap gambar QR code (data base64) dari elemen halaman.
   - Mengembalikan {qrcode_id, qrcode_base64}.
2. check_status(qr_id):
   - Polling status login: NEW -> SCANNED -> CONFIRMED / EXPIRED.
   - Saat user konfirmasi di aplikasi Shopee HP:
     Deteksi cookies SPC_EC / SPC_U atau redirect keluar dari halaman login.
   - Simpan cookies ke data/shopee_cookies.json.
   - Tutup sesi browser Chrome.
3. cancel_qr(qr_id):
   - Membatalkan dan menutup sesi headless browser jika user menutup modal.
"""
import base64
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import requests
from playwright.sync_api import sync_playwright

from config import C

logger = logging.getLogger("shopee_auth")

COOKIE_PATH = os.path.join(os.path.dirname(C.DB_PATH) or "data", "shopee_cookies.json")

# User Agent modern Chrome desktop
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# Argumen Chromium anti-deteksi yang terbukti lolos WAF Shopee (dipakai QR login)
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--window-size=1280,800",
]


def launch_stealth_browser(playwright):
    """Luncurkan Chromium headless dengan fingerprint anti-deteksi bot.

    Dipakai bersama oleh alur QR login dan fetch produk — satu fingerprint
    yang sudah terbukti lolos WAF Shopee.
    """
    browser = playwright.chromium.launch(
        channel="chrome",
        headless=True,
        args=STEALTH_ARGS,
    )
    return browser


def new_stealth_context(browser):
    """Buat browser context + inject cookies login Shopee yang tersimpan.

    Mengembalikan (context, page) yang siap dipakai. Jika tidak ada cookies
    tersimpan, context tetap dibuat tanpa cookies (tetap fingerprint asli).
    """
    context = browser.new_context(
        user_agent=DESKTOP_UA,
        viewport={"width": 1280, "height": 800},
        locale="id-ID",
    )
    cookies = load_cookies()
    if cookies:
        context.add_cookies([
            {"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
            for k, v in cookies.items()
            if isinstance(v, str) and v
        ])
    page = context.new_page()
    # Hapus flag webdriver agar tidak terdeteksi bot
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return context, page

# Global worker reference & lock
_current_worker = None
_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---- Cookie persistence ----

def save_cookies(cookies_dict):
    """Simpan cookies dict ke file JSON."""
    os.makedirs(os.path.dirname(COOKIE_PATH) or ".", exist_ok=True)
    payload = {
        "cookies": cookies_dict,
        "saved_at": _now(),
    }
    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_cookies():
    """Muat cookies dict dari file, atau None jika tidak ada / rusak."""
    if not os.path.isfile(COOKIE_PATH):
        return None
    try:
        with open(COOKIE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies")
        if cookies and isinstance(cookies, dict):
            return cookies
    except Exception:
        pass
    return None


def clear_cookies():
    """Hapus file cookies (logout)."""
    if os.path.isfile(COOKIE_PATH):
        try:
            os.remove(COOKIE_PATH)
        except Exception:
            pass


def is_logged_in():
    """Cek apakah ada cookies sesi Shopee yang tersimpan."""
    c = load_cookies()
    return bool(c and (c.get("SPC_EC") or c.get("SPC_U")))


def get_session():
    """Kembalikan requests.Session dengan cookies Shopee, atau None."""
    cookies = load_cookies()
    if not cookies:
        return None
    s = requests.Session()
    s.headers.update({
        "User-Agent": DESKTOP_UA,
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    })
    for k, v in cookies.items():
        s.cookies.set(k, v, domain=".shopee.co.id")
    return s


# ---- Playwright Worker Thread ----

class ShopeeQRWorker(threading.Thread):
    def __init__(self, session_id):
        super().__init__(daemon=True, name=f"ShopeeQR-{session_id}")
        self.session_id = session_id
        self.ready_event = threading.Event()
        self.stop_requested = False

        self.qr_base64 = None
        self.status = "INITIALIZING"  # INITIALIZING, NEW, SCANNED, CONFIRMED, EXPIRED, ERROR
        self.logged_in = False
        self.error = None
        self.cookies = {}

    def run(self):
        playwright = None
        browser = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-size=1280,800",
                ],
            )
            context = browser.new_context(
                user_agent=DESKTOP_UA,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            # Hapus flag webdriver agar tidak terdeteksi bot
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page.goto("https://shopee.co.id/buyer/login/qr", wait_until="networkidle", timeout=30000)

            # Tutup popup pilihan bahasa jika muncul
            try:
                lang_btn = page.query_selector("button:has-text('Bahasa Indonesia')")
                if lang_btn:
                    lang_btn.click()
                    page.wait_for_timeout(600)
            except Exception:
                pass

            # Tunggu elemen QR Code muncul
            page.wait_for_selector(".zFPfur, [class*='qrcode'], canvas", timeout=15000)
            page.wait_for_timeout(400)

            # 1. Screenshot elemen QR container (menghasilkan gambar lengkap dengan logo Shopee resmi di tengah)
            qr_b64 = None
            el = (
                page.query_selector(".zFPfur")
                or page.query_selector(".lnKhB7")
                or page.query_selector("[class*='qrcode']")
            )
            if el:
                try:
                    png_bytes = el.screenshot(type="png")
                    qr_b64 = base64.b64encode(png_bytes).decode("utf-8")
                except Exception:
                    pass

            # 2. Fallback ambil dari style background-image .zFPfur
            if not qr_b64:
                qr_b64 = page.evaluate("""() => {
                    const el = document.querySelector('.zFPfur') || document.querySelector('[class*="zFPfur"]');
                    if (el) {
                        const style = el.getAttribute('style') || '';
                        const m = style.match(/data:image\\/png;base64,([^"\\)]+)/);
                        if (m) return m[1];
                    }
                    return null;
                }""")

            if not qr_b64:
                raise RuntimeError("Elemen QR Code tidak ditemukan pada halaman Shopee.")

            self.qr_base64 = qr_b64
            self.status = "NEW"
            self.ready_event.set()

            # Loop pemantauan login (maks 150 detik)
            start_time = time.time()
            while not self.stop_requested and (time.time() - start_time < 150):
                page.wait_for_timeout(1000)

                # Ambil cookies terbaru dari browser context
                curr_cookies = context.cookies()
                cookie_map = {c["name"]: c["value"] for c in curr_cookies}
                curr_url = page.url

                # Cek tanda login sukses: ada SPC_EC atau SPC_U atau redirect keluar dari halaman login
                is_auth_cookie = bool(cookie_map.get("SPC_EC") or cookie_map.get("SPC_U"))
                is_redirected = ("shopee.co.id" in curr_url and "/buyer/login" not in curr_url and cookie_map.get("SPC_F"))

                if is_auth_cookie or is_redirected:
                    self.cookies = cookie_map
                    save_cookies(cookie_map)
                    self.status = "CONFIRMED"
                    self.logged_in = True
                    break

                # Cek teks status pada halaman (SCANNED / EXPIRED)
                try:
                    body_text = page.inner_text("body")
                    if any(w in body_text for w in ["Scan Berhasil", "Silakan konfirmasi", "di ponsel Anda", "dipindai"]):
                        if self.status != "SCANNED":
                            self.status = "SCANNED"
                    elif (time.time() - start_time > 20) and any(w in body_text for w in ["kedaluwarsa", "muat ulang", "Expired"]):
                        self.status = "EXPIRED"
                        break
                except Exception:
                    pass

            if not self.logged_in and self.status not in ("CONFIRMED", "EXPIRED"):
                self.status = "EXPIRED"

        except Exception as e:
            self.error = str(e)
            self.status = "ERROR"
            self.ready_event.set()
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

    def stop(self):
        self.stop_requested = True


# ---- Public API ----

def generate_qr():
    """Minta QR code baru via headless Chrome. Kembalikan {qrcode_id, qrcode_base64}."""
    global _current_worker

    session_id = base64.b32encode(os.urandom(5)).decode("utf-8").lower()
    with _lock:
        if _current_worker and _current_worker.is_alive():
            _current_worker.stop()
        worker = ShopeeQRWorker(session_id)
        _current_worker = worker
        worker.start()

    if not worker.ready_event.wait(timeout=30):
        worker.stop()
        raise RuntimeError(worker.error or "Gagal memuat QR Code Shopee (timeout)")

    if worker.error or not worker.qr_base64:
        worker.stop()
        raise RuntimeError(worker.error or "Gagal menghasilkan QR Code Shopee")

    return {
        "qrcode_id": worker.session_id,
        "qrcode_base64": worker.qr_base64,
    }


def check_status(qr_id):
    """Polling status QR login. Kembalikan dict {status, logged_in}.

    status: NEW | SCANNED | CONFIRMED | EXPIRED | ERROR
    """
    with _lock:
        worker = _current_worker

    if not worker or worker.session_id != qr_id:
        # Jika session worker sudah selesai tapi user sudah berhasil login
        if is_logged_in():
            return {"status": "CONFIRMED", "logged_in": True}
        return {"status": "EXPIRED", "logged_in": False, "error": "Sesi QR tidak aktif"}

    return {
        "status": worker.status,
        "logged_in": worker.logged_in,
        "error": worker.error,
    }


def cancel_qr(qr_id=None):
    """Hentikan worker dan tutup browser Chrome."""
    global _current_worker
    with _lock:
        if _current_worker:
            if not qr_id or _current_worker.session_id == qr_id:
                _current_worker.stop()
                _current_worker = None
