"""Generate gambar storyboard.

Provider (diatur via IMAGE_PROVIDER di .env):
- "openai" (default): API OpenAI-compatible, mis. 9Router text-to-image.
  api_key = IMAGE_API_KEY atau LLM_API_KEY;
  base_url = IMAGE_BASE_URL atau LLM_BASE_URL;
  model = IMAGE_MODEL (default: ag/gemini-3.1-flash-image).
- "pollinations": gratis, tanpa API key (model flux).
Hasil disimpan ke path lokal oleh pemanggil via download().
"""
import os
import urllib.parse

import requests

from config import C

# Rasio panel 9:16. Grid 2x2 -> keseluruhan tetap 9:16. Grid 5x2 -> landscape.
SIZES = {
    "2x2": (768, 1360),
    "5x2": (1408, 800),
}


def build_url(prompt, grid="2x2"):
    w, h = SIZES.get(grid, SIZES["2x2"])
    q = urllib.parse.quote(prompt[:1500])
    if C.IMAGE_PROVIDER == "openai":
        return None  # ditangani via API, bukan URL
    return (
        f"https://image.pollinations.ai/prompt/{q}"
        f"?width={w}&height={h}&nologo=true&model=flux&seed={abs(hash(prompt)) % 10_000_000}"
    )


def download(prompt, dest_path, grid="2x2", timeout=180):
    """Generate lalu unduh gambar ke dest_path. Kembalikan dest_path."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if C.IMAGE_PROVIDER == "openai":
        return _download_openai(prompt, dest_path, grid, timeout)
    url = build_url(prompt, grid)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(r.content)
    return dest_path


def _download_openai(prompt, dest_path, grid, timeout):
    import base64

    from openai import OpenAI

    api_key = C.IMAGE_API_KEY or C.LLM_API_KEY
    base_url = C.IMAGE_BASE_URL or C.LLM_BASE_URL
    model = C.IMAGE_MODEL or "ag/gemini-3.1-flash-image"

    if not api_key:
        raise RuntimeError("API key belum diisi untuk image provider openai / 9router (LLM_API_KEY atau IMAGE_API_KEY)")

    w, h = SIZES.get(grid, SIZES["2x2"])
    size = "1024x1792" if h > w else "1792x1024"
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    resp = client.images.generate(
        model=model,
        prompt=prompt[:1000],
        size=size,
        n=1,
        response_format="b64_json",
    )
    item = resp.data[0]
    if getattr(item, "b64_json", None):
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
