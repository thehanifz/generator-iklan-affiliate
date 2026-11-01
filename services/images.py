"""Generate gambar storyboard.

Provider default: pollinations (gratis, tanpa API key).
Alternatif: openai (model image, butuh LLM_API_KEY).
Hasil disimpan ke path lokal oleh pemanggil via download().

download() mendukung gambar referensi (ref_images): bila diisi dan provider
openai/9Router, generate memakai images.edit (image-to-image) agar hasil
mirip produk asli; gagal -> fallback otomatis ke text-to-image biasa.
"""
import os
import tempfile
import urllib.parse

import requests

from config import C

# Rasio panel 9:16. Grid 2x2 -> keseluruhan tetap 9:16. Grid 5x2 -> landscape.
SIZES = {
    "2x2": (768, 1360),
    "5x2": (1408, 800),
}

REF_PROMPT_SUFFIX = (
    "\n\nPENTING: Pertahankan desain, bentuk, warna, dan detail produk "
    "pada gambar referensi semirip mungkin. Jangan mengubah logo atau "
    "ciri khas produk."
)


def build_url(prompt, grid="2x2"):
    w, h = SIZES.get(grid, SIZES["2x2"])
    q = urllib.parse.quote(prompt[:1500])
    if C.IMAGE_PROVIDER == "openai":
        return None  # ditangani via API, bukan URL
    return (
        f"https://image.pollinations.ai/prompt/{q}"
        f"?width={w}&height={h}&nologo=true&model=flux&seed={abs(hash(prompt)) % 10_000_000}"
    )


def download(prompt, dest_path, grid="2x2", timeout=180, ref_images=None):
    """Generate lalu unduh gambar ke dest_path. Kembalikan dest_path.

    ref_images: list URL/path gambar referensi (opsional). Hanya dipakai
    provider openai/9Router via images.edit; provider lain mengabaikannya.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if C.IMAGE_PROVIDER == "openai":
        return _download_openai(prompt, dest_path, grid, timeout, ref_images)
    url = build_url(prompt, grid)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(r.content)
    return dest_path


def _fetch_local(url_or_path, timeout=60):
    """Kembalikan path file lokal untuk URL/path gambar. Unduh bila perlu."""
    if os.path.isfile(url_or_path):
        return url_or_path
    r = requests.get(url_or_path, timeout=timeout)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "")
    if "image" not in ctype and len(r.content) < 1024:
        raise RuntimeError(f"URL bukan gambar (content-type: {ctype})")
    fd, tmp = tempfile.mkstemp(suffix=".jpg", prefix="ref_")
    with os.fdopen(fd, "wb") as f:
        f.write(r.content)
    return tmp


def _save_image_response(resp, dest_path, timeout=120):
    """Simpan hasil images.generate / images.edit ke dest_path."""
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        import base64

        data = base64.b64decode(item.b64_json)
        with open(dest_path, "wb") as f:
            f.write(data)
    elif getattr(item, "url", None):
        r = requests.get(item.url, timeout=timeout)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
    else:
        raise RuntimeError("Tidak ada data gambar (b64_json / url) dari response model image")
    return dest_path


def _download_openai(prompt, dest_path, grid, timeout, ref_images=None):
    from openai import OpenAI

    api_key = C.IMAGE_API_KEY or C.LLM_API_KEY
    base_url = C.IMAGE_BASE_URL or C.LLM_BASE_URL
    model = C.IMAGE_MODEL or "ag/gemini-3.1-flash-image"

    if not api_key:
        raise RuntimeError("API key belum diisi untuk image provider openai / 9router (LLM_API_KEY atau IMAGE_API_KEY)")

    w, h = SIZES.get(grid, SIZES["2x2"])
    size = "1024x1792" if h > w else "1792x1024"
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    # --- image-to-image bila ada referensi ---
    ref_files = []
    for u in (ref_images or [])[:2]:
        try:
            ref_files.append(_fetch_local(u, timeout=min(60, timeout)))
        except Exception as e:
            print(f"[images] gambar referensi dilewati: {e}")
    if ref_files:
        try:
            with open(ref_files[0], "rb") as f:
                resp = client.images.edit(
                    model=model,
                    image=f,
                    prompt=(prompt[:1000] + REF_PROMPT_SUFFIX),
                    size=size,
                    n=1,
                    response_format="b64_json",
                )
            print("[images] generate via image-edit (dengan referensi produk).")
            return _save_image_response(resp, dest_path, timeout)
        except Exception as e:
            print(f"[images] image-edit gagal, fallback ke text-to-image: {e}")

    # --- text-to-image biasa ---
    resp = client.images.generate(
        model=model,
        prompt=prompt[:1000],
        size=size,
        n=1,
        response_format="b64_json",
    )
    return _save_image_response(resp, dest_path, timeout)
