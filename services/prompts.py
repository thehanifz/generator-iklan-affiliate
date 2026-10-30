"""Template prompt LLM per mode.

Mode iklan    : gaya NARA — fokus produk, 1 konsep, 10 scene, 1 storyboard (5x2).
Mode affiliate: ikut pola skill v2 — 1 konsep affiliate, segmen 8 detik,
                4 shot/segmen, storyboard 1 lembar per segmen (2x2),
                prompt base + extend, voiceover Bahasa Indonesia + CTA.
"""

SYSTEM_ID = (
    "Kamu adalah creative director iklan video pendek vertikal 9:16 untuk affiliate marketing Indonesia. "
    "Bahasa: Bahasa Indonesia santai ala kreator. Jangan mengarang harga, diskon, atau spesifikasi "
    "yang tidak ada di data produk. Jangan klaim berlebihan."
)

IKLAN_CONCEPT = """Buatkan 1 KONSEP IKLAN produk (fokus produk, bukan affiliate) dari data berikut.

Produk: {title}
Harga: {price}
Deskripsi: {description}
Karakter: {character} ({char_desc})

Format jawaban persis:
JUDUL KONSEP: ...
ANGLE: ... (1 kalimat)
RINGKASAN: ... (1-2 kalimat)
Lalu daftar 10 SCENE, masing-masing 1 baris dengan format:
Scene N: [visual 1 kalimat] | Teks layar: "[maks 4 kata]"
Urutan: hook -> intro produk -> 3 detail produk -> pemakaian -> lifestyle -> OOTD -> harga -> CTA.
Teks layar singkat, punchy, tanpa emoji berlebihan."""


def iklan_storyboard_prompt(concept_text, title):
    return (
        "Create a professional commercial storyboard sheet with exactly 10 sequential panels "
        "in a 5 columns x 2 rows layout, clean white borders, each panel vertical 9:16, "
        "for a 9:16 product advertisement video. One panel per scene, numbered Scene 1 to Scene 10, "
        "clear scene-number labels on each panel.\n\n"
        f"Product: {title}, identical across all panels. Preserve exact shape, colors, label.\n"
        "Photorealistic, studio-quality lighting, no CGI look, no watermarks, no floating objects.\n\n"
        f"Scene list:\n{concept_text}\n\n"
        "Consistent product identity and lighting across all panels."
    )


IKLAN_VIDEO_PROMPT = """Berdasarkan konsep dan 10 scene berikut, tulis 1 PROMPT VIDEO lengkap siap pakai
untuk generate video vertikal 9:16 (format umum, durasi total ±20 detik, 10 scene).

Sertakan: instruksi umum, format 9:16, daftar scene dengan timestamp (0:00-0:02 dst),
gerakan kamera per scene, konsistensi produk, transisi antar scene, dan saran audio/musik.

Konsep & scene:
{concept_text}
Produk: {title}
Karakter: {character}"""


AFFILIATE_CONCEPT = """Buatkan 1 KONSEP IKLAN AFFILIATE dari data berikut.

Produk: {title}
Harga: {price}
Deskripsi: {description}
Karakter: {character} ({char_desc})
Durasi: {duration} detik = {segments} segmen @8 detik.

Format jawaban persis:
JUDUL KONSEP: ...
ANGLE: ... (1 kalimat)
RINGKASAN: ... (1-2 kalimat)
Lalu SHOT LIST per segmen. Tiap segmen 4 shot @±2 detik dengan format:
Segmen N, Shot M (t1-t2): [visual 1 kalimat] | Audio: [foley/musik] | Transisi: [jenis]
Pola tiap segmen: hook -> detail produk -> aksi pemakaian -> closing segmen.
Segmen 2+ MELANJUTKAN dari frame terakhir segmen sebelumnya (jangan restart adegan).
Lalu NASKAH VOICEOVER Bahasa Indonesia per segmen (±18-20 kata per 8 detik,
gaya kreator affiliate natural, segmen terakhir diakhiri CTA "Cek produknya sekarang!").
Latar/environment SAMA di semua segmen — tentukan 1 setting dan tulis di baris:
SETTING: ..."""


def affiliate_storyboard_prompt(seg_index, total_seg, shot_text, title):
    return (
        "Create a professional commercial storyboard sheet with exactly 4 sequential panels "
        "in a 2x2 grid layout, clean white borders, each panel vertical 9:16, "
        f"for segment {seg_index} of {total_seg} of a 9:16 affiliate advertisement (8 seconds). "
        "One panel per shot, descriptions match the shot list exactly, in order.\n\n"
        f"Product reference: {title}, identical to reference. Preserve exact proportions, colors, geometry, label.\n"
        "Photorealistic, realistic lighting, no CGI, no watermarks, no floating objects, no invented features.\n\n"
        f"Shot list:\n{shot_text}\n\n"
        "Consistent character, wardrobe, product identity and environment across all panels."
    )


AFFILIATE_VIDEO_BASE = """Tulis PROMPT VIDEO segmen 1 (base, 8 detik, vertikal 9:16) siap pakai untuk AI video generator,
berdasarkan shot list berikut. Sertakan: PRODUCT LOCK (nama + deskripsi fisik persis produk, jangan diubah),
gaya kamera, SHOT LIST dengan timestamp 0:00-0:08, audio/foley per shot, transisi,
dan VOICEOVER Bahasa Indonesia (±18-20 kata, natural).

Shot list:
{shot_text}
Produk: {title}
Karakter: {character} ({char_desc})
Setting: {setting}"""

AFFILIATE_VIDEO_EXTEND = """Tulis PROMPT VIDEO extend (8 detik berikutnya) yang MELANJUTKAN video dari frame
terakhirnya secara mulus (seamless extend). Produk, karakter, wardrobe, setting, dan
pencahayaan SAMA PERSIS — jangan restart adegan. Sertakan PRODUCT LOCK, SHOT LIST lanjutan
dengan timestamp, audio/foley, transisi, dan VOICEOVER Bahasa Indonesia (±18-20 kata,
melanjutkan narasi, diakhiri CTA "Cek produknya sekarang!").

Shot list lanjutan:
{shot_text}
Produk: {title}
Karakter: {character}"""


def build_tasks(mode, llm_chat, product, character):
    """Jalankan LLM sesuai mode. Kembalikan dict hasil terstruktur.

    product: dict(title, price, description)
    character: dict(name, description)
    """
    title = product.get("title", "")
    ctx = {
        "title": title,
        "price": product.get("price", "-"),
        "description": product.get("description", "-")[:800],
        "character": character.get("name", "-"),
        "char_desc": character.get("description", "-"),
    }
    if mode == "iklan":
        concept = llm_chat(SYSTEM_ID, IKLAN_CONCEPT.format(**ctx), max_tokens=1500)
        sb_prompt = iklan_storyboard_prompt(concept, title)
        video_prompt = llm_chat(
            SYSTEM_ID,
            IKLAN_VIDEO_PROMPT.format(concept_text=concept, **ctx),
            max_tokens=2000,
        )
        return {
            "concept": concept,
            "storyboards": [{"grid": "5x2", "prompt": sb_prompt, "label": "storyboard"}],
            "video_prompt": video_prompt,
            "duration": "±20 detik",
        }
    # affiliate
    duration = 16
    segments = 2
    concept_full = llm_chat(
        SYSTEM_ID,
        AFFILIATE_CONCEPT.format(duration=duration, segments=segments, **ctx),
        max_tokens=2000,
    )
    # Pisahkan shot list per segmen secara sederhana (berdasarkan baris "Segmen N")
    seg_shots = _split_segments(concept_full, segments)
    setting = _extract_setting(concept_full)
    storyboards = []
    for i, shots in enumerate(seg_shots, start=1):
        storyboards.append(
            {
                "grid": "2x2",
                "prompt": affiliate_storyboard_prompt(i, segments, shots, title),
                "label": f"storyboard segmen {i}",
            }
        )
    base_prompt = llm_chat(
        SYSTEM_ID,
        AFFILIATE_VIDEO_BASE.format(shot_text=seg_shots[0], setting=setting, **ctx),
        max_tokens=2000,
    )
    extend_prompt = llm_chat(
        SYSTEM_ID,
        AFFILIATE_VIDEO_EXTEND.format(shot_text=seg_shots[1] if len(seg_shots) > 1 else seg_shots[0], **ctx),
        max_tokens=2000,
    )
    video_prompt = (
        "=== PROMPT VIDEO SEGMEN 1 (BASE) ===\n" + base_prompt
        + "\n\n=== PROMPT VIDEO SEGMEN 2 (EXTEND) ===\n" + extend_prompt
    )
    return {
        "concept": concept_full,
        "storyboards": storyboards,
        "video_prompt": video_prompt,
        "duration": f"{duration} detik",
    }


def _split_segments(text, n):
    import re

    parts = re.split(r"(?im)^.*segmen\s+(\d+).*?$", text)
    # parts: [pre, num1, body1, num2, body2, ...]
    bodies = [parts[i] for i in range(2, len(parts), 2)]
    while len(bodies) < n:
        bodies.append(text)
    return [b.strip()[:1200] for b in bodies[:n]]


def _extract_setting(text):
    import re

    m = re.search(r"(?im)^setting\s*:\s*(.+)$", text)
    return m.group(1).strip() if m else "-"
