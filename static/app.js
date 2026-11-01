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

let catTomSelect = null;
let subTomSelect = null;
let charTomSelect = null;

function api(path, opts = {}) {
  const url = state.token ? `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(state.token)}` : path;
  return fetch(url, opts).then(async (r) => {
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  });
}

function toast(msg) {
  const t = $("toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 2500);
}

function show(view) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $(view).classList.remove("hidden");
  window.scrollTo(0, 0);
}

function errBox(id, msg) {
  const e = $(id);
  if (!e) return;
  if (!msg) { e.classList.add("hidden"); return; }
  e.textContent = msg;
  e.classList.remove("hidden");
}

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function copyShopeeLink(e, link) {
  if (e) e.stopPropagation();
  if (!link) {
    toast("Link Shopee tidak tersedia");
    return;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(() => {
      toast("Link Shopee disalin ✓");
    }).catch(() => {
      fallbackCopy(link);
    });
  } else {
    fallbackCopy(link);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
    toast("Link Shopee disalin ✓");
  } catch (err) {
    toast("Gagal menyalin link");
  }
  document.body.removeChild(ta);
}

/* ---------- mode ---------- */
$("modeIklan").onclick = () => setMode("iklan");
$("modeAffiliate").onclick = () => setMode("affiliate");
function setMode(m) {
  state.mode = m;
  $("modeIklan").classList.toggle("active", m === "iklan");
  $("modeAffiliate").classList.toggle("active", m === "affiliate");
}

/* ---------- inisialisasi tomselect ---------- */
function initCatSelect() {
  if (window.TomSelect && $("catSelect") && !catTomSelect) {
    try {
      catTomSelect = new TomSelect("#catSelect", {
        create: false,
        controlInput: null, // Klik murni, tanpa kursor mengetik
        maxOptions: 100,
        placeholder: "— Pilih Kategori —",
        allowEmptyOption: true,
        render: {
          option: (data, escape) => {
            if (!data.value) return `<div class="cat-option"><span class="cat-option-name">${escape(data.text)}</span></div>`;
            return `<div class="cat-option">
              <span class="cat-option-name">${escape(data.text)}</span>
              ${data.count !== undefined ? `<span class="cat-option-count">${data.count}</span>` : ""}
            </div>`;
          },
          item: (data, escape) => {
            if (!data.value) return `<span>${escape(data.text)}</span>`;
            return `<span>${escape(data.text)}${data.count !== undefined ? ` (${data.count})` : ""}</span>`;
          }
        },
        onChange: (val) => {
          state.cat = val || "";
          state.sub = "";
          renderSubSelect();
          loadProducts();
        }
      });
    } catch (e) {
      console.warn("TomSelect catSelect init error:", e);
    }
  }
}

function initSubSelect() {
  if (window.TomSelect && $("subSelect") && !subTomSelect) {
    try {
      subTomSelect = new TomSelect("#subSelect", {
        create: false,
        controlInput: null, // Klik murni
        maxOptions: 150,
        placeholder: "Semua sub-kategori",
        allowEmptyOption: true,
        onChange: (val) => {
          state.sub = val || "";
          if (state.cat) loadProducts();
        }
      });
    } catch (e) {
      console.warn("TomSelect subSelect init error:", e);
    }
  }
}

function initCharSelect() {
  if (window.TomSelect && $("characterSelect") && !charTomSelect) {
    try {
      charTomSelect = new TomSelect("#characterSelect", {
        create: false,
        controlInput: null, // Klik murni
        valueField: "id",
        labelField: "name",
        searchField: ["name", "description"],
        placeholder: "— Tanpa karakter —",
        allowEmptyOption: true,
        render: {
          option: (data, escape) => {
            if (!data.id) return `<div class="char-option"><span>${escape(data.name || "— Tanpa karakter —")}</span></div>`;
            return `<div class="char-option">
              ${data.photo_url ? `<img src="${escape(data.photo_url)}" class="char-option-img">` : '<div class="char-option-img"></div>'}
              <div>
                <div class="char-option-name">${escape(data.name || "")}</div>
                ${data.description ? `<div class="char-option-desc">${escape(data.description)}</div>` : ""}
              </div>
            </div>`;
          },
          item: (data, escape) => {
            if (!data.id) return `<span>${escape(data.name || "— Tanpa karakter —")}</span>`;
            return `<div class="char-option">
              ${data.photo_url ? `<img src="${escape(data.photo_url)}" class="char-option-img" style="width:20px;height:20px;">` : ""}
              <span>${escape(data.name || "")}</span>
            </div>`;
          }
        }
      });
    } catch (e) {
      console.warn("TomSelect characterSelect init error:", e);
    }
  }
}

/* ---------- karakter ---------- */
async function loadCharacters() {
  try {
    const j = await api("/api/characters");
    const chars = j.characters || [];
    
    if (charTomSelect) {
      charTomSelect.clear();
      charTomSelect.clearOptions();
      charTomSelect.addOption({ id: "", name: "— Tanpa karakter —", description: "", photo_url: "" });
      chars.forEach((c) => charTomSelect.addOption(c));
      charTomSelect.setValue("");
      charTomSelect.refreshOptions(false);
    } else {
      const sel = $("characterSelect");
      if (sel) {
        sel.innerHTML = '<option value="">— Tanpa karakter —</option>';
        chars.forEach((c) => {
          const o = document.createElement("option");
          o.value = c.id;
          o.textContent = c.name;
          sel.appendChild(o);
        });
      }
    }

    const list = $("charList");
    if (list) {
      list.innerHTML = "";
      chars.forEach((c) => {
        const d = document.createElement("div");
        d.className = "char-item";
        d.innerHTML = `${c.photo_url ? `<img src="${c.photo_url}">` : ""}<span>${esc(c.name)}</span>`;
        const del = document.createElement("button");
        del.textContent = "✕";
        del.title = "Hapus";
        del.onclick = async () => {
          if (confirm(`Hapus karakter ${c.name}?`)) {
            await api(`/api/characters/${c.id}`, { method: "DELETE" });
            loadCharacters();
          }
        };
        d.appendChild(del);
        list.appendChild(d);
      });
    }
  } catch (e) { /* abaikan jika API belum siap */ }
}

$("charAddBtn").onclick = () => $("charForm").classList.toggle("hidden");
const charCancel = $("charCancelBtn");
if (charCancel) charCancel.onclick = () => $("charForm").classList.add("hidden");

$("charSaveBtn").onclick = async () => {
  const nameVal = $("charName").value.trim();
  if (!nameVal) { toast("Nama karakter wajib diisi"); return; }
  const fd = new FormData();
  fd.append("name", nameVal);
  fd.append("description", $("charDesc").value);
  if ($("charPhoto").files[0]) fd.append("photo", $("charPhoto").files[0]);
  try {
    await api("/api/characters", { method: "POST", body: fd });
    $("charForm").classList.add("hidden");
    $("charName").value = "";
    $("charDesc").value = "";
    $("charPhoto").value = "";
    loadCharacters();
    toast("Karakter berhasil ditambahkan");
  } catch (e) {
    toast("Gagal: " + e.message);
  }
};

/* ---------- upload tempat ---------- */
$("placeBox").onclick = (e) => { if (e.target.tagName !== "BUTTON") $("placePhoto").click(); };
$("placePhoto").onchange = () => {
  const f = $("placePhoto").files[0]; if (!f) return;
  $("placePreview").src = URL.createObjectURL(f); $("placePreview").classList.remove("hidden");
  $("placeName").textContent = f.name; $("placeRemove").classList.remove("hidden");
};
$("placeRemove").onclick = (e) => {
  e.stopPropagation(); $("placePhoto").value = ""; $("placePreview").classList.add("hidden");
  $("placeName").textContent = ""; $("placeRemove").classList.add("hidden");
};

/* ========== TAHAP 1: DASHBOARD ========== */
async function loadCategories() {
  try {
    const j = await api("/api/catalog/categories");
    state.categories = j.categories || [];
    renderCatDropdown();
  } catch (e) {
    const el = $("catSelect");
    if (el) el.closest(".sidebar-block").innerHTML = `<div class="alert-box error">Gagal memuat kategori: ${esc(e.message)}</div>`;
  }
}

function renderCatDropdown() {
  if (!state.categories.length) return;

  if (catTomSelect) {
    catTomSelect.clear();
    catTomSelect.clearOptions();
    catTomSelect.addOption({ value: "", text: "— Pilih Kategori —", count: undefined });
    state.categories.forEach((c) => {
      catTomSelect.addOption({
        value: c.kategori,
        text: c.kategori,
        count: c.count || 0
      });
    });
    catTomSelect.setValue(state.cat || "");
    catTomSelect.refreshOptions(false);
  } else {
    const sel = $("catSelect");
    if (!sel) return;
    sel.innerHTML = '<option value="">— Pilih Kategori —</option>';
    state.categories.forEach((c) => {
      const o = document.createElement("option");
      o.value = c.kategori;
      o.textContent = `${c.kategori} (${c.count || 0})`;
      sel.appendChild(o);
    });
  }
  renderSubSelect();
}

function renderSubSelect() {
  const c = state.categories.find((x) => x.kategori === state.cat);
  const subList = c ? c.sub || [] : [];

  if (subTomSelect) {
    subTomSelect.clear();
    subTomSelect.clearOptions();
    subTomSelect.addOption({ value: "", text: "Semua sub-kategori" });
    subList.forEach((s) => subTomSelect.addOption({ value: s, text: s }));
    subTomSelect.setValue(state.sub || "");
    subTomSelect.refreshOptions(false);
  } else {
    const sel = $("subSelect");
    if (!sel) return;
    sel.innerHTML = '<option value="">Semua sub-kategori</option>';
    subList.forEach((s) => {
      const o = document.createElement("option");
      o.value = s;
      o.textContent = s;
      if (state.sub === s) o.selected = true;
      sel.appendChild(o);
    });
  }
}

let searchTimer = null;
$("searchInput").oninput = (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.q = e.target.value.trim();
    if (state.cat) loadProducts();
  }, 350);
};

async function loadProducts() {
  const grid = $("productGrid");

  // Jika belum memilih kategori: tampilkan empty state ramah
  if (!state.cat) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📁</div>
        <h3>Pilih Kategori Produk</h3>
        <p>Silakan pilih kategori dari panel kiri untuk memuat daftar produk.</p>
      </div>`;
    return;
  }

  grid.innerHTML = '<div class="loading">Memuat produk dari database…</div>';
  try {
    const p = new URLSearchParams();
    p.set("kategori", state.cat);
    if (state.sub) p.set("sub", state.sub);
    if (state.q) p.set("q", state.q);
    const j = await api("/api/catalog/products?" + p.toString());
    state.products = j.products || [];
    renderGrid();
  } catch (e) {
    grid.innerHTML = `<div class="alert-box error">Gagal memuat produk: ${esc(e.message)}</div>`;
  }
}

function isSelected(pid) { return state.selected.some((s) => s.id === pid); }

function renderGrid() {
  const grid = $("productGrid");
  grid.innerHTML = "";

  if (!state.cat) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📁</div>
        <h3>Pilih Kategori Produk</h3>
        <p>Silakan pilih kategori dari panel kiri untuk memuat daftar produk.</p>
      </div>`;
    return;
  }

  if (!state.products.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h3>Tidak ada produk yang cocok</h3>
        <p>Coba pilih sub-kategori lain atau ganti kata kunci pencarian Anda.</p>
      </div>`;
    return;
  }

  state.products.forEach((p) => {
    const sel = state.selected.find((s) => s.id === p.id);
    const card = document.createElement("div");
    card.className = "pcard" + (sel ? " selected" : "");
    card.innerHTML = `
      ${sel && sel.utama ? '<span class="badge-utama">⭐ UTAMA</span>' : ""}
      <div class="pcard-img-wrap">
        ${p.thumb ? `<img src="${esc(p.thumb)}" alt="" loading="lazy">` : '<div class="noimg">📷</div>'}
      </div>
      <div class="pcard-body">
        <div class="pcard-name" title="${esc(p.nama)}">${esc(p.nama)}</div>
        <div class="pcard-meta">
          <span class="pcard-price">${esc(p.harga || "")}</span>
          ${p.link_shopee ? `<button type="button" class="btn-copy-shopee" title="Salin link Shopee" onclick="copyShopeeLink(event, '${esc(p.link_shopee)}')">📋 Salin Link</button>` : ''}
        </div>
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
  if (!bar) return;
  if (!state.selected.length) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  const countEl = $("selectCount");
  if (countEl) countEl.textContent = `${state.selected.length} / ${MAX_SELECT}`;
  const main = state.selected.find((s) => s.utama);
  const mainEl = $("mainLabel");
  if (mainEl) {
    mainEl.innerHTML = main
      ? `⭐ <b>${esc(main.nama.slice(0, 30))}</b> <button type="button" id="changeMainBtn" class="btn btn-outline btn-xs">Ganti</button>`
      : "";
  }
  const cb = $("changeMainBtn");
  if (cb) cb.onclick = (e) => {
    e.stopPropagation();
    const i = state.selected.findIndex((s) => s.utama);
    state.selected.forEach((s) => (s.utama = false));
    state.selected[(i + 1) % state.selected.length].utama = true;
    renderGrid();
  };
}
$("clearSelectBtn").onclick = () => { state.selected = []; renderGrid(); };

$("resetBtn").onclick = () => {
  state.selected = []; state.cat = ""; state.sub = ""; state.q = "";
  $("searchInput").value = "";
  if (catTomSelect) catTomSelect.setValue("");
  if (subTomSelect) { subTomSelect.clear(); subTomSelect.clearOptions(); subTomSelect.addOption({ value: "", text: "Semua sub-kategori" }); subTomSelect.setValue(""); }
  if (charTomSelect) charTomSelect.setValue("");
  $("placeRemove").onclick({ stopPropagation() {} });
  setMode("affiliate"); errBox("formError", "");
  renderGrid();
};

$("nextBtn").onclick = async () => {
  errBox("formError", "");
  if (!state.selected.length) { errBox("formError", "Pilih minimal 1 produk dari katalog terlebih dahulu."); return; }
  show("view-preview");
  await renderPhotoPreview();
};

/* ========== TAHAP 2: PILIH FOTO ========== */
async function renderPhotoPreview() {
  const wrap = $("photoSections");
  wrap.innerHTML = '<div class="loading">Memuat foto produk dari Drive…</div>';
  errBox("previewError", "");
  state.chosen = {};
  for (const s of state.selected) {
    try {
      const j = await api(`/api/catalog/products/${encodeURIComponent(s.id)}/photos`);
      state.photos[s.id] = j.photos || [];
    } catch (e) {
      state.photos[s.id] = [];
    }
    state.chosen[s.id] = state.photos[s.id].map((p) => p.full);
  }
  wrap.innerHTML = "";
  state.selected.forEach((s) => {
    const sec = document.createElement("div");
    sec.className = "photo-section";
    const photos = state.photos[s.id] || [];
    sec.innerHTML = `<h3>${s.utama ? "⭐ " : ""}${esc(s.nama)} <small>(${photos.length} foto tersedia)</small></h3>
      <div class="photo-grid"></div>`;
    const grid = sec.querySelector(".photo-grid");
    if (!photos.length) grid.innerHTML = '<div class="loading">Tidak ada foto dalam folder Drive.</div>';
    photos.forEach((ph) => {
      const d = document.createElement("div");
      d.className = "photo-item selected";
      // Gunakan proxy lokal /api/drive-image/<file_id> agar anti-blokir dan bisa langsung diunduh
      const proxyUrl = ph.id && ph.id !== "utama" ? `/api/drive-image/${encodeURIComponent(ph.id)}` : ph.thumb;
      const downloadUrl = ph.id && ph.id !== "utama" ? `/api/drive-image/${encodeURIComponent(ph.id)}?download=1` : ph.full;
      d.innerHTML = `
        <img src="${proxyUrl}" alt="" loading="lazy">
        <span class="photo-check">✓</span>
        <a href="${downloadUrl}" class="photo-dl-btn" title="Unduh foto ini" download onclick="event.stopPropagation()">⬇</a>
      `;
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
      errBox("previewError", `Pilih minimal 1 foto untuk produk: ${s.nama.slice(0, 50)}`);
      return;
    }
  }
  const fd = new FormData();
  fd.append("mode", state.mode);
  const charVal = charTomSelect ? charTomSelect.getValue() : $("characterSelect").value;
  fd.append("character_id", charVal || "");
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
  $("processTitle").textContent = "Memproses Konten Anda"; $("processSub").textContent = "Mohon tunggu, AI sedang menyusun materi…";
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
  try { await navigator.clipboard.writeText($("promptText").textContent); toast("Prompt tersalin ke clipboard ✓"); }
  catch (e) { toast("Clipboard diblokir browser — salin manual dari kotak teks."); }
};
$("dlStoryboardBtn").onclick = () => {
  document.querySelectorAll("#storyboards img").forEach((img, i) => {
    const a = document.createElement("a"); a.href = img.src; a.download = `storyboard-${i + 1}.png`; a.target = "_blank"; a.click();
  });
};

/* Inisialisasi awal */
initCatSelect();
initSubSelect();
initCharSelect();
loadCharacters();
loadCategories();
