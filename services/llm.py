"""Wrapper LLM OpenAI-compatible (OpenAI, 9Router, dll)."""
from openai import OpenAI

from config import C

_client = None


def _client_or_raise():
    global _client
    if not C.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY belum diisi di .env")
    if _client is None:
        _client = OpenAI(base_url=C.LLM_BASE_URL, api_key=C.LLM_API_KEY)
    return _client


def chat(system, user, max_tokens=2000, temperature=0.7):
    """Kirim 1 percakapan, kembalikan teks balasan."""
    client = _client_or_raise()
    resp = client.chat.completions.create(
        model=C.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()
