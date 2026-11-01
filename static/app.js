/* Generator Iklan & Affiliate v2 — alur database:
   dashboard (pilih ≤5 produk) -> pilih foto -> proses -> hasil */
const $ = (id) => document.getElementById(id);
const state = {
  mode: "affiliate", jobId: null, pollTimer: null, lastLogId: 0,
  token: new URLSearchParams(location.search).get("token") || "",
  categories: [], products: [], selected: [], // selected: [{id,nama,harga,thumb,utama}]
  photos: {}, // pid -> [{id,name,thumb,full}]
  chosen: {}, // pid -> [full urls]
  cat: "", sub: "", q: "",
};
const STAGES = ["Memvalidasi input", "Mengambil informasi produk", "Menganalisis foto karakter dan tempat", "Menyusun storyboard", "Membuat prompt video", "Menyiapkan hasil akhir"];
const MAX_SELECT = 5;

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
function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

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
      d.innerHTML = `${c.photo_url ? `<img src="${c.photo_url}">` : ""}<span>${esc(c.name)}</span>`;
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

/* ========== TAHAP 1: DASHBOARD ========== */
async function loadCategories() {
  try {
    const j = await api("/api/catalog/categories");
    state.categories = j.categories || [];
    renderCatPills();
  } catch (e) {
    $("catPills").innerHTML = `<div class="error">Gagal memuat kategori: ${esc(e.message)}</div>`;
  }
}

function renderCatPills() {
  const wrap = $("catPills"); wrap.innerHTML = "";
  const all = document.createElement("button");
  all.type = "button"; all.className = "pill" + (state.cat === "" ? " active" : ""); all.textContent = "Semua";
  all.onclick = () => { state.cat = ""; state.sub = ""; renderCatPills(); loadProducts(); };
  wrap.appendChild(all);
  state.categories.forEach((c) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "pill" + (state.cat === c.kategori ? " active" : ""); b.textContent = c.kategori;
    b.onclick = () => { state.cat = c.kategori; state.sub = ""; renderCatPills(); loadProducts(); };
    wrap.appendChild(b);
  });
  renderSubSelect();
}

function renderSubSelect() {
  const sel = $("subSelect");
  sel.innerHTML = '<option value="">Semua sub-kategori</option>';
  const c = state.categories.find((x) => x.kategori === state.cat);
  (c ? c.sub : []).forEach((s) => {
    const o = document.createElement("option"); o.value = s; o.textContent = s;
    if (state.sub === s) o.selected = true;
    sel.appendChild(o);
  });
}
$("subSelect").onchange = (e) => { state.sub = e.target.value; loadProducts(); };

let searchTimer = null;
$("searchInput").oninput = (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = e.target.value.trim(); loadProducts(); }, 400);
};

async function loadProducts() {
  const grid = $("productGrid");
  grid.innerHTML = '<div class="loading">Memuat produk…</div>';
  try {
    const p = new URLSearchParams();
    if (state.cat) p.set("kategori", state.cat);
    if (state.sub) p.set("sub", state.sub);
    if (state.q) p.set("q", state.q);
    const j = await api("/api/catalog/products?" + p.toString());
    state.products = j.products || [];
    renderGrid();
  } catch (e) {
    grid.innerHTML = `<div class="error">Gagal memuat produk: ${esc(e.message)}</div>`;
  }
}

function isSelected(pid) { return state.selected.some((s) => s.id === pid); }

function renderGrid() {
  const grid = $("productGrid"); grid.innerHTML = "";
  if (!state.products.length) { grid.innerHTML = '<div class="loading">Tidak ada produk.</div>'; return; }
  state.products.forEach((p) => {
    const sel = state.selected.find((s) => s.id === p.id);
    const card = document.createElement("div");
    card.className = "pcard" + (sel ? " selected" : "");
    card.innerHTML = `
      ${sel && sel.utama ? '<span class="badge-utama">⭐ UTAMA</span>' : ""}
      ${p.thumb ? `<img src="${esc(p.thumb)}" alt="" loading="lazy">` : '<div class="noimg">📷</div>'}
      <div class="pcard-body">
        <div class="pcard-name">${esc(p.nama)}</div>
        <div class="pcard-price">${esc(p.harga || "")}</div>
      </div>
      <div class="pcard-check">${sel ? "✓" : ""}</div>`;
    card.onclick = () => toggleSelect(p);
    grid.appendChild(card);
  });
  renderSelectBar();
}

function toggleSelect(p) {
  const idx = state.selected.findIndex((s) => s.id === p.id);
  if (idx >= 0) {
    const removed = state.selected.splice(idx, 1)[0];
    if (removed.utama && state.selected.length) state.selected[0].utama = true;
  } else {
    if (state.selected.length >= MAX_SELECT) { toast(`Maksimal ${MAX_SELECT} produk`); return; }
    state.selected.push({ id: p.id, nama: p.nama, harga: p.harga, thumb: p.thumb, utama: state.selected.length === 0 });
  }
  renderGrid();
}

function renderSelectBar() {
  const bar = $("selectBar");
  if (!state.selected.length) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  $("selectCount").textContent = `${state.selected.length}/${MAX_SELECT} dipilih`;
  const main = state.selected.find((s) => s.utama);
  $("mainLabel").innerHTML = main
    ? `⭐ Utama: <b>${esc(main.nama.slice(0, 40))}</b> <button type="button" id="changeMainBtn" class="btn small">Ganti</button>`
    : "";
  const cb = $("changeMainBtn");
  if (cb) cb.onclick = (e) => {
    e.stopPropagation();
    // putar produk utama ke pilihan berikutnya
    const i = state.selected.findIndex((s) => s.utama);
    state.selected.forEach((s) => (s.utama = false));
    state.selected[(i + 1) % state.selected.length].utama = true;
    renderGrid();
  };
}
$("clearSelectBtn").onclick = () => { state.selected = []; renderGrid(); };

$("resetBtn").onclick = () => {
  state.selected = []; state.cat = ""; state.sub = ""; state.q = "";
  $("searchInput").value = ""; $("subSelect").value = "";
  $("placeRemove").onclick({ stopPropagation() {} });
  setMode("affiliate"); errBox("formError", "");
  renderCatPills(); loadProducts();
};

$("nextBtn").onclick = async () => {
  errBox("formError", "");
  if (!state.selected.length) { errBox("formError", "Pilih minimal 1 produk dari dashboard."); return; }
  show("view-preview");
  await renderPhotoPreview();
};

/* ========== TAHAP 2: PILIH FOTO ========== */
async function renderPhotoPreview() {
  const wrap = $("photoSections");
  wrap.innerHTML = '<div class="loading">Memuat foto produk…</div>';
  errBox("previewError", "");
  state.chosen = {};
  for (const s of state.selected) {
    try {
      const j = await api(`/api/catalog/products/${encodeURIComponent(s.id)}/photos`);
      state.photos[s.id] = j.photos || [];
    } catch (e) {
      state.photos[s.id] = [];
    }
    // default: semua foto terpilih
    state.chosen[s.id] = state.photos[s.id].map((p) => p.full);
  }
  wrap.innerHTML = "";
  state.selected.forEach((s) => {
    const sec = document.createElement("div");
    sec.className = "photo-section";
    const photos = state.photos[s.id] || [];
    sec.innerHTML = `<h3>${s.utama ? "⭐ " : ""}${esc(s.nama)} <small>(${photos.length} foto)</small></h3>
      <div class="photo-grid"></div>`;
    const grid = sec.querySelector(".photo-grid");
    if (!photos.length) grid.innerHTML = '<div class="loading">Tidak ada foto.</div>';
    photos.forEach((ph) => {
      const d = document.createElement("div");
      d.className = "photo-item selected";
      d.innerHTML = `<img src="${esc(ph.thumb)}" alt="" loading="lazy"><span class="photo-check">✓</span>`;
      d.onclick = () => {
        const i = state.chosen[s.id].indexOf(ph.full);
        if (i >= 0) { state.chosen[s.id].splice(i, 1); d.classList.remove("selected"); }
        else { state.chosen[s.id].push(ph.full); d.classList.add("selected"); }
      };
      grid.appendChild(d);
    });
    wrap.appendChild(sec);
  });
}
$("backBtn").onclick = () => show("view-form");

/* ---------- buat job & proses ---------- */
$("processBtn").onclick = async () => {
  errBox("previewError", "");
  for (const s of state.selected) {
    if (!state.chosen[s.id] || !state.chosen[s.id].length) {
      errBox("previewError", `Pilih minimal 1 foto untuk: ${s.nama.slice(0, 50)}`);
      return;
    }
  }
  const fd = new FormData();
  fd.append("mode", state.mode);
  fd.append("character_id", $("characterSelect").value);
  if ($("placePhoto").files[0]) fd.append("place_photo", $("placePhoto").files[0]);
  fd.append("products_json", JSON.stringify(
    state.selected.map((s) => ({ id: s.id, utama: s.utama, photos: state.chosen[s.id] }))
  ));
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
loadCategories();
loadProducts();
