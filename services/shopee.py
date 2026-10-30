"""Ambil info produk dari link atau teks share Shopee.

Mendukung:
1. Teks share resmi aplikasi Shopee:
   "Cek <Judul> dengan harga <Harga>. Dapatkan di Shopee sekarang! <URL>"
2. URL langsung (shopee.co.id, s.shopee.co.id, shope.ee)
3. Fallback graceful jika Shopee memblokir scraping otomatis (captcha):
   tetap mengembalikan data yang berhasil diparsing tanpa melempar fatal error,
   sehingga pengguna dapat melengkapi atau mengeditnya di UI.
"""
import html
import logging
import re
import requests

from config import C

logger = logging.getLogger("shopee")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


def parse_shopee_text(input_text):
    """Ekstrak judul, harga, dan URL dari teks share Shopee."""
    raw = (input_text or "").strip()

    # Format 1: Standar share teks aplikasi Shopee Indonesia:
    # "Cek <Judul> dengan harga <Harga>. Dapatkan di Shopee sekarang! <URL>"
    m1 = re.search(
        r"Cek\s+(.+?)\s+dengan harga\s+(.+?)\.?\s+Dapatkan di Shopee sekarang!\s*(https?://\S+)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if m1:
        return {
            "title": m1.group(1).strip(),
            "price": m1.group(2).strip().rstrip("."),
            "url": m1.group(3).strip(),
        }

    # Format 2: Ekstrak URL http(s)
    url_match = re.search(r"(https?://(?:s\.shopee\.co\.id|shope\.ee|shopee\.co\.id)/\S+)", raw)
    url = url_match.group(1) if url_match else raw

    # Cari harga (Rp ...)
    price_match = re.search(r"(Rp\s*[\d\.,]+)", raw, re.IGNORECASE)
    price = price_match.group(1).strip() if price_match else ""

    # Cari nama produk dari sisa teks jika bukan sekedar URL
    cleaned = raw.replace(url, "")
    if price:
        cleaned = cleaned.replace(price, "")
    cleaned = re.sub(
        r"\b(Cek|Beli|Dapatkan di Shopee sekarang!?|dengan harga|cek produk buat tes)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"^[.,!?:;\-\s]+|[.,!?:;\-\s]+$", "", cleaned)
    title = cleaned if len(cleaned) >= 3 else ""

    return {
        "title": title,
        "price": price,
        "url": url,
    }


def _get_session():
    """Kembalikan requests session, pakai cookies Shopee jika tersedia."""
    try:
        from services.shopee_auth import get_session
        s = get_session()
        if s:
            return s
    except Exception:
        pass
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def resolve_url(url, timeout=15):
    """Resolve short URL (s.shopee.co.id / shope.ee) ke URL tujuan."""
    if not url.startswith(("http://", "https://")):
        return url
    try:
        s = _get_session()
        # Gunakan GET dengan stream=True agar ringan tapi mengikuti redirect secara akurat
        r = s.get(url, allow_redirects=True, timeout=timeout, stream=True)
        try:
            return r.url
        finally:
            r.close()
    except Exception:
        return url


def _meta(page, prop):
    m = re.search(
        r'<meta[^>]+property=["\']' + re.escape(prop) + r'["\'][^>]+content=["\']([^"\']+)',
        page,
        re.IGNORECASE,
    )
    if m:
        return html.unescape(m.group(1).strip())
    m = re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']' + re.escape(prop) + r'["\']',
        page,
        re.IGNORECASE,
    )
    return html.unescape(m.group(1).strip()) if m else ""


def _looks_like_challenge(page_html):
    """Deteksi halaman captcha-shell WAF Shopee.

    Shopee mengembalikan HTTP 200 berisi halaman anti-bot (tanpa og: meta tags)
    untuk HTTP client non-browser — harus dibedakan dari halaman produk asli.
    """
    if re.search(r'<meta[^>]+property=["\']og:title["\']', page_html, re.IGNORECASE):
        return False
    return bool(re.search(r'pcmall-captcha|stm-sg-live|__captcha|robot-check', page_html, re.IGNORECASE))


def fetch_meta_via_browser(url, timeout=30):
    """Ambil og: meta tags produk via headless Chromium (Playwright).

    Fallback ketika `requests` diblokir WAF Shopee. Memakai fingerprint stealth
    yang sama dengan alur QR login (services.shopee_auth) + cookies login yang
    tersimpan di data/shopee_cookies.json, sehingga Shopee menyajikan halaman
    produk asli — bukan captcha-shell.

    Hanya dipanggil bila jalur cepat gagal total (judul masih kosong), jadi
    link yang datanya sudah lengkap dari teks share tidak ikut melambat.

    Kembalikan dict {title, price, image, description}; kosong bila gagal.
    """
    out = {"title": "", "price": "", "image": "", "description": ""}
    try:
        from playwright.sync_api import sync_playwright
        from services import shopee_auth
    except ImportError:
        logger.warning("playwright tidak terinstal, fallback browser dilewati")
        return out

    playwright = None
    browser = None
    context = None
    try:
        playwright = sync_playwright().start()
        browser = shopee_auth.launch_stealth_browser(playwright)
        context, page = shopee_auth.new_stealth_context(browser)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        # og:title hanya ada di halaman produk asli, bukan captcha-shell
        try:
            page.wait_for_selector('meta[property="og:title"]', timeout=12000)
        except Exception:
            pass
        data = page.evaluate(
            """() => {
                const get = (p) => {
                    const el = document.querySelector('meta[property="' + p + '"]');
                    return el ? (el.getAttribute('content') || '').trim() : '';
                };
                return {
                    title: get('og:title'),
                    price: get('product:price:amount') || get('og:price:amount'),
                    image: get('og:image'),
                    description: get('og:description'),
                };
            }"""
        )
        if isinstance(data, dict):
            for k in out:
                if data.get(k):
                    out[k] = data[k]
    except Exception as e:
        logger.warning("fetch_meta_via_browser gagal: %s", e)
    finally:
        for obj, meth in ((context, "close"), (browser, "close"), (playwright, "stop")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass
    return out


def fetch_product(url_or_text, timeout=20):
    """Kembalikan dict {url, title, price, image, rating, description}.

    Jika judul dan harga berhasil diekstrak dari teks share, langsung dipakai.
    Jika perlu scraping web, dilakukan secara best-effort tanpa memblokir alur jika Shopee WAF menolak.
    """
    parsed = parse_shopee_text(url_or_text)
    url = parsed["url"]
    title = parsed["title"]
    price = parsed["price"]
    image = ""
    desc = ""
    rating = ""

    # Jika URL kosong tapi ada input
    if not url.startswith(("http://", "https://")):
        if title:
            return {
                "url": url_or_text,
                "title": title,
                "price": price,
                "image": image,
                "rating": rating,
                "description": desc,
            }
        raise RuntimeError("Link produk tidak valid (harus berupa URL Shopee)")

    # Jika judul dan harga sudah ada dari teks share, kita sudah punya data primer yang valid!
    final_url = resolve_url(url)

    # Coba scraping meta tags secara best effort untuk mendapatkan foto / deskripsi
    try:
        s = _get_session()
        r = s.get(final_url, timeout=timeout)
        try:
            if r.status_code == 200:
                page = r.text
                # WAF Shopee memberi HTTP 200 berisi captcha-shell untuk client
                # non-browser — jangan perlakukan sebagai halaman produk.
                if _looks_like_challenge(page):
                    logger.info("WAF Shopee memblokir requests; coba fallback browser")
                else:
                    meta_title = _meta(page, "og:title")
                    meta_image = _meta(page, "og:image")
                    meta_desc = _meta(page, "og:description")
                    meta_price = _meta(page, "product:price:amount") or _meta(page, "og:price:amount")

                    # Jangan pakai generic Shopee title
                    if meta_title and "Shopee" not in meta_title:
                        title = title or meta_title
                    if meta_image:
                        image = meta_image
                    if meta_desc:
                        desc = meta_desc[:500]
                    if meta_price:
                        price = price or meta_price
        finally:
            r.close()
    except Exception:
        pass

    # Fallback browser: HANYA bila judul masih kosong (preview akan gagal).
    # Headless Chromium lolos WAF Shopee (fingerprint browser asli + cookies
    # login), jadi link telanjang tetap bisa diproses — dengan tambahan waktu.
    if not title:
        bmeta = fetch_meta_via_browser(final_url)
        if bmeta["title"] and "Shopee" not in bmeta["title"]:
            title = bmeta["title"]
        if bmeta["image"]:
            image = bmeta["image"]
        if bmeta["description"]:
            desc = bmeta["description"][:500]
        if bmeta["price"]:
            price = price or bmeta["price"]

    # Jika judul masih kosong (misal user hanya memasukkan link pendek tanpa teks share dan scraping diblokir)
    if not title:
        # Coba ambil potongan kata dari path URL jika ada nama produk
        m_slug = re.search(r"shopee\.co\.id/([^/?]+)-i\.\d+\.\d+", final_url)
        if m_slug:
            slug = m_slug.group(1).replace("-", " ").strip()
            if len(slug) > 3:
                title = slug.title()

    return {
        "url": final_url or url,
        "title": title,
        "price": price,
        "image": image,
        "rating": rating,
        "description": desc,
        "needs_manual_input": not bool(title),
    }
