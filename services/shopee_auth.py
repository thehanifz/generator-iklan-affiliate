"""Login Shopee via Akun Manual (Playwright Chrome) & QR Code.

Alur Manual:
1. start_manual_login(username, password):
   - Membuka browser Chrome nyata (headed) ke https://shopee.co.id/buyer/login.
   - Mengisi username & password secara otomatis (dari .env SHOPEE_USER / SHOPEE_PASS atau input UI).
   - Mengklik tombol 'LOG IN'.
   - Jika ada verifikasi (OTP SMS/WhatsApp/puzzle slider), pengguna dapat langsung
     menyelesaikannya di jendela browser Chrome yang sedang terbuka.
   - Begitu login berhasil, cookies sesi (SPC_EC, SPC_U, SPC_ST) otomatis disimpan
     ke data/shopee_cookies.json dan jendela Chrome ditutup otomatis.
2. check_manual_status(session_id):
   - Polling status login manual: RUNNING -> CONFIRMED / EXPIRED / ERROR.
3. cancel_manual_login(session_id):
   - Membatalkan dan menutup sesi browser manual.
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

# Argumen Chromium anti-deteksi yang terbukti lolos WAF Shopee
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--window-size=1280,850",
]


def launch_stealth_browser(playwright, headless=True):
    """Luncurkan Chromium headless/headed dengan fingerprint anti-deteksi bot."""
    browser = playwright.chromium.launch(
        channel="chrome",
        headless=headless,
        args=STEALTH_ARGS,
    )
    return browser


def new_stealth_context(browser):
    """Buat browser context + inject cookies login Shopee yang tersimpan."""
    context = browser.new_context(
        user_agent=DESKTOP_UA,
        viewport={"width": 1280, "height": 850},
        locale="id-ID",
    )
    context.add_cookies([
        {"name": "shopee_web_lang", "value": "id", "domain": ".shopee.co.id", "path": "/"},
    ])
    cookies = load_cookies()
    if cookies:
        context.add_cookies([
            {"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
            for k, v in cookies.items()
            if isinstance(v, str) and v
        ])
    page = context.new_page()
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
    return bool(c and (c.get("SPC_EC") or c.get("SPC_U") or c.get("SPC_ST")))


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


# ---- Manual Login Worker Thread ----

class ShopeeManualLoginWorker(threading.Thread):
    def __init__(self, session_id, username=None, password=None):
        super().__init__(daemon=True, name=f"ShopeeManualLogin-{session_id}")
        self.session_id = session_id
        self.username = username or C.SHOPEE_USER
        self.password = password or C.SHOPEE_PASS
        self.ready_event = threading.Event()
        self.stop_requested = False

        self.status = "STARTING"  # STARTING, RUNNING, CONFIRMED, ERROR, CANCELLED
        self.logged_in = False
        self.error = None
        self.cookies = {}

    def run(self):
        playwright = None
        browser = None
        try:
            playwright = sync_playwright().start()
            # Buka browser Chrome dengan headless=False agar pengguna bisa melihat layar
            # dan menyelesaikan verifikasi OTP / SMS / WhatsApp / puzzle jika diminta.
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1280,850",
                ],
            )
            context = browser.new_context(
                user_agent=DESKTOP_UA,
                viewport={"width": 1280, "height": 850},
                locale="id-ID",
            )
            context.add_cookies([
                {"name": "shopee_web_lang", "value": "id", "domain": ".shopee.co.id", "path": "/"},
            ])
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page.goto("https://shopee.co.id/buyer/login", wait_until="networkidle", timeout=45000)

            # Tutup popup pilihan bahasa jika ada
            try:
                page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button, div, [role="button"]'));
                    for (const b of buttons) {
                        if (b.textContent.trim() === 'Bahasa Indonesia') {
                            b.click();
                            break;
                        }
                    }
                    document.querySelectorAll('.SqO999, .UsynuF, .pEpvVk, [class*="shopee-popup"]').forEach(m => m.remove());
                }""")
                page.wait_for_timeout(400)
            except Exception:
                pass

            # Isi input username & password jika ada
            if self.username:
                try:
                    user_input = page.wait_for_selector(
                        "input[name='loginKey'], input[placeholder*='Handphone'], input[placeholder*='Username'], input[placeholder*='Email']",
                        timeout=10000,
                    )
                    if user_input:
                        user_input.fill(self.username)
                        page.wait_for_timeout(300)
                except Exception as e:
                    logger.warning("Gagal mengisi username Shopee: %s", e)

            if self.password:
                try:
                    pass_input = page.wait_for_selector(
                        "input[name='password'], input[type='password']",
                        timeout=6000,
                    )
                    if pass_input:
                        pass_input.fill(self.password)
                        page.wait_for_timeout(300)
                except Exception as e:
                    logger.warning("Gagal mengisi password Shopee: %s", e)

            # Jika username & password lengkap, klik tombol Log In
            if self.username and self.password:
                try:
                    btn = page.query_selector("button:has-text('LOG IN'), button:has-text('Log In'), button[type='submit']")
                    if btn:
                        btn.click()
                        page.wait_for_timeout(1000)
                except Exception as e:
                    logger.warning("Gagal klik tombol login Shopee: %s", e)

            self.status = "RUNNING"
            self.ready_event.set()

            # Pantau sesi sampai login berhasil (maksimal 300 detik = 5 menit)
            start_time = time.time()
            while not self.stop_requested and (time.time() - start_time < 300):
                page.wait_for_timeout(1000)

                # Jika pengguna menutup browser Chrome secara manual
                try:
                    if page.is_closed():
                        if not self.logged_in:
                            self.status = "CANCELLED"
                        break
                except Exception:
                    break

                curr_cookies = context.cookies()
                cookie_map = {c["name"]: c["value"] for c in curr_cookies}
                curr_url = page.url

                is_auth_cookie = bool(cookie_map.get("SPC_EC") or cookie_map.get("SPC_U") or cookie_map.get("SPC_ST"))
                is_redirected = ("shopee.co.id" in curr_url and "/buyer/login" not in curr_url and cookie_map.get("SPC_F"))

                if is_auth_cookie or is_redirected:
                    self.cookies = cookie_map
                    save_cookies(cookie_map)
                    self.status = "CONFIRMED"
                    self.logged_in = True
                    # Beri jeda 1 detik agar pengguna melihat tanda sukses sebelum ditutup
                    page.wait_for_timeout(1000)
                    break

            if not self.logged_in and self.status not in ("CONFIRMED", "CANCELLED"):
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


# ---- QR Login Worker Thread ----

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
                locale="id-ID",
            )
            context.add_cookies([
                {"name": "shopee_web_lang", "value": "id", "domain": ".shopee.co.id", "path": "/"},
            ])
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Tangkap langsung QR code murni dari respons resmi API Shopee
            captured_qr = {"b64": None, "id": None}
            def on_response(res):
                if "gen_qrcode" in res.url:
                    try:
                        data = res.json()
                        d = data.get("data") or {}
                        if d.get("qrcode_base64"):
                            captured_qr["b64"] = d["qrcode_base64"]
                        if d.get("qrcode_id"):
                            captured_qr["id"] = d["qrcode_id"]
                    except Exception:
                        pass

            page.on("response", on_response)
            page.goto("https://shopee.co.id/buyer/login/qr", wait_until="networkidle", timeout=30000)

            # Klik tombol 'Bahasa Indonesia' pada popup jika ada
            try:
                page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button, div, [role="button"]'));
                    for (const b of buttons) {
                        if (b.textContent.trim() === 'Bahasa Indonesia') {
                            b.click();
                            break;
                        }
                    }
                    document.querySelectorAll('.SqO999, .UsynuF, .pEpvVk, [class*="shopee-popup"]').forEach(m => m.remove());
                }""")
            except Exception:
                pass

            qr_b64 = captured_qr["b64"]
            if not qr_b64:
                try:
                    qr_b64 = page.evaluate("""() => {
                        const el = document.querySelector('.zFPfur') || document.querySelector('[class*="zFPfur"]');
                        if (el) {
                            const style = el.getAttribute('style') || '';
                            const m = style.match(/data:image\\/png;base64,([^"\\)]+)/);
                            if (m) return m[1];
                        }
                        return null;
                    }""")
                except Exception:
                    pass

            if not qr_b64:
                try:
                    page.wait_for_selector(".zFPfur, [class*='qrcode'], canvas", timeout=5000)
                    el = page.query_selector(".zFPfur") or page.query_selector("[class*='qrcode']")
                    if el:
                        png_bytes = el.screenshot(type="png")
                        qr_b64 = base64.b64encode(png_bytes).decode("utf-8")
                except Exception:
                    pass

            if not qr_b64:
                raise RuntimeError("Elemen QR Code tidak ditemukan pada halaman Shopee.")

            self.qr_base64 = qr_b64
            self.status = "NEW"
            self.ready_event.set()

            start_time = time.time()
            while not self.stop_requested and (time.time() - start_time < 150):
                page.wait_for_timeout(1000)
                curr_cookies = context.cookies()
                cookie_map = {c["name"]: c["value"] for c in curr_cookies}
                curr_url = page.url

                is_auth_cookie = bool(cookie_map.get("SPC_EC") or cookie_map.get("SPC_U") or cookie_map.get("SPC_ST"))
                is_redirected = ("shopee.co.id" in curr_url and "/buyer/login" not in curr_url and cookie_map.get("SPC_F"))

                if is_auth_cookie or is_redirected:
                    self.cookies = cookie_map
                    save_cookies(cookie_map)
                    self.status = "CONFIRMED"
                    self.logged_in = True
                    break

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


# ---- Public API (Manual & QR) ----

def start_manual_login(username=None, password=None):
    """Mulai proses login manual Shopee (membuka peramban Chrome)."""
    global _current_worker

    session_id = base64.b32encode(os.urandom(5)).decode("utf-8").lower()
    with _lock:
        if _current_worker and _current_worker.is_alive():
            _current_worker.stop()
        worker = ShopeeManualLoginWorker(session_id, username=username, password=password)
        _current_worker = worker
        worker.start()

    if not worker.ready_event.wait(timeout=30):
        worker.stop()
        raise RuntimeError(worker.error or "Gagal membuka halaman login Shopee (timeout)")

    if worker.error:
        worker.stop()
        raise RuntimeError(worker.error)

    return {
        "session_id": worker.session_id,
        "status": worker.status,
    }


def check_manual_status(session_id):
    """Polling status login manual. Kembalikan dict {status, logged_in}."""
    with _lock:
        worker = _current_worker

    if is_logged_in():
        return {"status": "CONFIRMED", "logged_in": True}

    if not worker or worker.session_id != session_id:
        return {"status": "EXPIRED", "logged_in": False, "error": "Sesi login tidak aktif"}

    return {
        "status": worker.status,
        "logged_in": worker.logged_in,
        "error": worker.error,
    }


def cancel_manual_login(session_id=None):
    """Hentikan worker login manual."""
    global _current_worker
    with _lock:
        if _current_worker:
            if not session_id or _current_worker.session_id == session_id:
                _current_worker.stop()
                _current_worker = None


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
    """Polling status QR login. Kembalikan dict {status, logged_in}."""
    with _lock:
        worker = _current_worker

    if not worker or worker.session_id != qr_id:
        if is_logged_in():
            return {"status": "CONFIRMED", "logged_in": True}
        return {"status": "EXPIRED", "logged_in": False, "error": "Sesi QR tidak aktif"}

    return {
        "status": worker.status,
        "logged_in": worker.logged_in,
        "error": worker.error,
    }


def cancel_qr(qr_id=None):
    """Hentikan worker QR."""
    global _current_worker
    with _lock:
        if _current_worker:
            if not qr_id or _current_worker.session_id == qr_id:
                _current_worker.stop()
                _current_worker = None
