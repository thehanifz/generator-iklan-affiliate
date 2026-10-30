/* Generator Iklan & Affiliate — vanilla JS, 4 tahap: form -> preview -> proses -> hasil */
const $ = (id) => document.getElementById(id);
const state = { mode: "affiliate", jobId: null, pollTimer: null, lastLogId: 0, preview: null, token: new URLSearchParams(location.search).get("token") || "" };
const STAGES = ["Memvalidasi input", "Mengambil informasi produk", "Menganalisis foto karakter dan tempat", "Menyusun storyboard", "Membuat prompt video", "Menyiapkan hasil akhir"];

function api(path, opts = {}) {
  const url = state.token ? `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(state.token)}` : path;
  return fetch(url, opts).then(async (r) => {
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  });
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.remove("hidden"); setTimeout(() => t.classList.add("hidden"), 2500); }
function show(view) { document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden")); $(view).classList.remove("hidden"); window.scrollTo(0, 0); }
function errBox(id, msg) { const e = $(id); if (!msg) { e.classList.add("hidden"); return; } e.textContent = msg; e.classList.remove("hidden"); }

/* ---------- mode ---------- */
$("modeIklan").onclick = () => setMode("iklan");
$("modeAffiliate").onclick = () => setMode("affiliate");
function setMode(m) {
  state.mode = m;
  $("modeIklan").classList.toggle("active", m === "iklan");
  $("modeAffiliate").classList.toggle("active", m === "affiliate");
}

/* ---------- karakter ---------- */
async function loadCharacters() {
  try {
    const j = await api("/api/characters");
    const sel = $("characterSelect");
    sel.innerHTML = '<option value="">— Tanpa karakter —</option>';
    const list = $("charList"); list.innerHTML = "";
    j.characters.forEach((c) => {
      const o = document.createElement("option"); o.value = c.id; o.textContent = c.name; sel.appendChild(o);
      const d = document.createElement("div"); d.className = "char-item";
      d.innerHTML = `${c.photo_url ? `<img src="${c.photo_url}">` : ""}<span>${c.name}</span>`;
      const del = document.createElement("button"); del.textContent = "✕"; del.title = "Hapus";
      del.onclick = async () => { if (confirm(`Hapus karakter ${c.name}?`)) { await api(`/api/characters/${c.id}`, { method: "DELETE" }); loadCharacters(); } };
      d.appendChild(del); list.appendChild(d);
    });
  } catch (e) { /* abaikan jika API belum siap */ }
}
$("charAddBtn").onclick = () => $("charForm").classList.toggle("hidden");
$("charSaveBtn").onclick = async () => {
  const fd = new FormData();
  fd.append("name", $("charName").value);
  fd.append("description", $("charDesc").value);
  if ($("charPhoto").files[0]) fd.append("photo", $("charPhoto").files[0]);
  try { await api("/api/characters", { method: "POST", body: fd }); $("charForm").classList.add("hidden"); $("charName").value = ""; $("charDesc").value = ""; loadCharacters(); toast("Karakter ditambahkan"); }
  catch (e) { toast("Gagal: " + e.message); }
};

/* ---------- upload tempat ---------- */
$("placeBox").onclick = (e) => { if (e.target.tagName !== "BUTTON") $("placePhoto").click(); };
$("placePhoto").onchange = () => {
  const f = $("placePhoto").files[0]; if (!f) return;
  $("placePreview").src = URL.createObjectURL(f); $("placePreview").classList.remove("hidden");
  $("placeName").textContent = f.name; $("placeRemove").classList.remove("hidden");
};
$("placeRemove").onclick = (e) => { e.stopPropagation(); $("placePhoto").value = ""; $("placePreview").classList.add("hidden"); $("placeName").textContent = ""; $("placeRemove").classList.add("hidden"); };

/* ---------- form ---------- */
$("resetBtn").onclick = () => { document.querySelectorAll("#view-form input[type=url], #view-form input[type=text]").forEach((i) => (i.value = "")); $("placeRemove").onclick({ stopPropagation() {} }); setMode("affiliate"); errBox("formError", ""); };
$("nextBtn").onclick = async () => {
  errBox("formError", "");
  const url = $("productUrl").value.trim();
  if (!url) { errBox("formError", "Link Produk Utama wajib diisi."); return; }
  show("view-preview"); $("previewLoading").classList.remove("hidden"); $("previewContent").classList.add("hidden"); errBox("previewError", "");
  try {
    const j = await api("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) });
    state.preview = j.product;
    renderPreview(j.product);
    $("previewLoading").classList.add("hidden"); $("previewContent").classList.remove("hidden");
  } catch (e) { $("previewLoading").classList.add("hidden"); errBox("previewError", e.message + " — periksa link lalu coba lagi, atau lanjutkan dan isi manual di tahap berikut."); $("previewContent").classList.remove("hidden"); renderPreview(null); }
};
function pCard(p, main) {
  if (!p) return `<div class="product-card"><div><b>Data produk tidak terbaca.</b><br><small>Lanjutkan untuk isi manual, atau kembali dan perbaiki link.</small></div></div>`;
  return `<div class="product-card">${p.image ? `<img src="${p.image}" alt="">` : ""}<div><b>${p.title || "-"}</b><br><span class="price">${p.price || ""}</span><br><small>${p.rating || ""} ${p.description ? "· " + p.description.slice(0, 120) : ""}</small></div></div>`;
}
async function renderPreview(main) {
  $("mainProductCard").innerHTML = pCard(main, true);
  const supGrid = $("supProducts"); supGrid.innerHTML = "";
  for (const inp of document.querySelectorAll(".supUrl")) {
    const u = inp.value.trim(); if (!u) continue;
    try { const j = await api("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: u }) }); supGrid.innerHTML += pCard(j.product); }
    catch (e) { supGrid.innerHTML += `<div class="product-card"><div><b>Gagal membaca:</b><br><small>${u}</small></div></div>`; }
  }
}
$("backBtn").onclick = () => show("view-form");

/* ---------- buat job & proses ---------- */
$("processBtn").onclick = async () => {
  const fd = new FormData();
  fd.append("mode", state.mode);
  fd.append("product_url", $("productUrl").value.trim());
  document.querySelectorAll(".supUrl").forEach((i) => { if (i.value.trim()) fd.append("supporting_urls", i.value.trim()); });
  fd.append("character_id", $("characterSelect").value);
  if ($("placePhoto").files[0]) fd.append("place_photo", $("placePhoto").files[0]);
  if (state.preview) { fd.append("product_title", state.preview.title || ""); fd.append("product_price", state.preview.price || ""); fd.append("product_image", state.preview.image || ""); }
  try {
    const j = await api("/api/jobs", { method: "POST", body: fd });
    startPolling(j.job_id);
  } catch (e) { errBox("previewError", e.message); }
};
function renderChecklist(currentStage, status) {
  const ul = $("checklist"); ul.innerHTML = "";
  STAGES.forEach((s, i) => {
    const li = document.createElement("li");
    let cls = "st-wait";
    if (status === "gagal" && i + 1 === currentStage) cls = "st-fail";
    else if (status === "story board ready") cls = "st-done";
    else if (i + 1 < currentStage) cls = "st-done";
    else if (i + 1 === currentStage) cls = "st-run";
    li.className = cls; li.textContent = `${i + 1}. ${s}`; ul.appendChild(li);
  });
}
function startPolling(jobId) {
  state.jobId = jobId; state.lastLogId = 0; $("logPanel").innerHTML = "";
  $("retryBtn").classList.add("hidden"); $("newJobBtn").classList.add("hidden");
  $("processTitle").textContent = "Memproses Konten Anda"; $("processSub").textContent = "Mohon tunggu, sistem sedang bekerja…";
  show("view-process");
  clearInterval(state.pollTimer);
  const tick = async () => {
    try {
      const j = await api(`/api/jobs/${jobId}`);
      const job = j.job;
      $("progressFill").style.width = job.progress + "%"; $("progressPct").textContent = job.progress + "%";
      renderChecklist(job.current_stage, job.status);
      const lj = await api(`/api/jobs/${jobId}/logs?since=${state.lastLogId}`);
      const panel = $("logPanel");
      lj.logs.forEach((l) => {
        state.lastLogId = Math.max(state.lastLogId, l.id);
        const div = document.createElement("div");
        if (l.level === "error") div.className = "err"; else if (l.level === "warning") div.className = "warn";
        div.textContent = `${l.ts.slice(11, 19)} — ${l.message}`;
        panel.appendChild(div);
      });
      panel.scrollTop = panel.scrollHeight;
      if (job.status === "story board ready") { clearInterval(state.pollTimer); showResult(jobId); }
      else if (job.status === "gagal") {
        clearInterval(state.pollTimer);
        $("processTitle").textContent = "Proses gagal"; $("processSub").textContent = job.error || "Terjadi kesalahan.";
        $("retryBtn").classList.remove("hidden"); $("newJobBtn").classList.remove("hidden");
      }
    } catch (e) { /* tunggu tick berikutnya */ }
  };
  tick(); state.pollTimer = setInterval(tick, 2000);
}
$("retryBtn").onclick = async () => { await api(`/api/jobs/${state.jobId}/retry`, { method: "POST" }); startPolling(state.jobId); };
$("newJobBtn").onclick = () => show("view-form");
$("resultNewBtn").onclick = () => show("view-form");

/* ---------- hasil ---------- */
async function showResult(jobId) {
  try {
    const j = await api(`/api/jobs/${jobId}/result`);
    const wrap = $("storyboards"); wrap.innerHTML = "";
    (j.storyboard_urls || []).forEach((u) => {
      // tampilkan dari file lokal bila tersedia via outputs, fallback link Drive
      const img = document.createElement("img"); img.src = u; img.alt = "storyboard"; wrap.appendChild(img);
    });
    if (!j.storyboard_urls || !j.storyboard_urls.length) wrap.innerHTML = "<p><small>File storyboard tersimpan di server (cek folder outputs).</small></p>";
    $("promptText").textContent = j.video_prompt || "";
    show("view-result");
  } catch (e) { toast("Gagal memuat hasil: " + e.message); }
}
$("copyPromptBtn").onclick = async () => {
  try { await navigator.clipboard.writeText($("promptText").textContent); toast("Prompt tersalin ✓"); }
  catch (e) { toast("Clipboard diblokir browser — salin manual dari kotak teks."); }
};
$("dlStoryboardBtn").onclick = () => {
  document.querySelectorAll("#storyboards img").forEach((img, i) => {
    const a = document.createElement("a"); a.href = img.src; a.download = `storyboard-${i + 1}.png`; a.target = "_blank"; a.click();
  });
};

loadCharacters();
