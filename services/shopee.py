"""Ambil info produk dari link Shopee (best-effort).

Shopee adalah SPA yang berat; fungsi ini mencoba:
1. Resolve short link (s.shopee.co.id) -> URL penuh.
2. Ambil meta tag og:title / og:image / og:description / product:price:amount.
Jika gagal (blokir/CAPTCHA), raise RuntimeError dengan pesan jelas
agar UI bisa menawarkan "Coba Lagi" atau "Isi Manual".
"""
import html
import re

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


def resolve_url(url, timeout=20):
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=timeout)
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


def fetch_product(url, timeout=30):
    """Kembalikan dict {url, title, price, image, rating, description}."""
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("Link produk harus berupa URL http(s)")
    final_url = resolve_url(url)
    try:
        r = requests.get(final_url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        page = r.text
    except Exception as e:
        raise RuntimeError(f"Tidak bisa mengambil data produk (kemungkinan diblokir Shopee): {e}")

    title = _meta(page, "og:title")
    image = _meta(page, "og:image")
    desc = _meta(page, "og:description")
    price = _meta(page, "product:price:amount") or _meta(page, "og:price:amount")
    if not title:
        # fallback: <title>
        m = re.search(r"<title>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
        title = html.unescape(m.group(1).strip()) if m else ""
    if not title:
        raise RuntimeError("Data produk tidak terbaca dari link (Shopee memblokir akses otomatis).")
    return {
        "url": final_url,
        "title": title,
        "price": price,
        "image": image,
        "rating": "",
        "description": desc[:500],
    }
