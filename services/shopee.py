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
import re
import requests

from config import C

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
        return r.url
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
        if r.status_code == 200:
            page = r.text
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
    except Exception:
        pass

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
