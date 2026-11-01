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

/* ========== Shopee Manual Login ========== */
let manualPollTimer = null;
let currentManualSessionId = null;

async function checkShopeeStatus() {
  try {
    const j = await api("/api/shopee/status");
    updateShopeeUI(j.logged_in);
    if (j.shopee_user && $("shopeeInputUser") && !$("shopeeInputUser").value) {
      $("shopeeInputUser").value = j.shopee_user;
    }
    if (j.has_credentials && $("shopeeInputPass")) {
      $("shopeeInputPass").placeholder = "•••••••• (sudah terisi dari .env)";
    }
  } catch (e) { /* ignore */ }
}

function updateShopeeUI(loggedIn) {
  if (loggedIn) {
    $("shopeeLoginBtn").classList.add("hidden");
    $("shopeeStatus").classList.remove("hidden");
    $("shopeeLogoutBtn").classList.remove("hidden");
  } else {
    $("shopeeLoginBtn").classList.remove("hidden");
    $("shopeeStatus").classList.add("hidden");
    $("shopeeLogoutBtn").classList.add("hidden");
  }
}

$("shopeeLoginBtn").onclick = () => {
  $("shopeeModal").classList.remove("hidden");
  $("manualLoginStatus").classList.add("hidden");
  $("manualLoginInstruction").classList.add("hidden");
  $("startManualLoginBtn").disabled = false;
  $("startManualLoginBtn").textContent = "🚀 Buka Browser & Login";
};

$("shopeeModalCloseBtn").onclick = () => closeShopeeModal();
$("shopeeModal").onclick = (e) => { if (e.target === $("shopeeModal")) closeShopeeModal(); };

function closeShopeeModal() {
  $("shopeeModal").classList.add("hidden");
  if (manualPollTimer) { clearInterval(manualPollTimer); manualPollTimer = null; }
  if (currentManualSessionId) {
    api("/api/shopee/login/manual/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentManualSessionId }),
    }).catch(() => {});
    currentManualSessionId = null;
  }
}

$("startManualLoginBtn").onclick = async () => {
  const username = $("shopeeInputUser") ? $("shopeeInputUser").value.trim() : "";
  const password = $("shopeeInputPass") ? $("shopeeInputPass").value.trim() : "";

  const statusBox = $("manualLoginStatus");
  statusBox.textContent = "⏳ Membuka peramban Chrome di desktop Anda...";
  statusBox.className = "qr-status-msg scanning";
  statusBox.classList.remove("hidden");
  $("manualLoginInstruction").classList.remove("hidden");
  $("startManualLoginBtn").disabled = true;
  $("startManualLoginBtn").textContent = "Browser Aktif...";

  try {
    const j = await api("/api/shopee/login/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!j.ok) throw new Error(j.error || "Gagal memulai browser");
    currentManualSessionId = j.session_id;

    startManualPolling(j.session_id);
  } catch (e) {
    statusBox.textContent = "❌ " + e.message;
    statusBox.className = "qr-status-msg expired";
    $("startManualLoginBtn").disabled = false;
    $("startManualLoginBtn").textContent = "Coba Lagi";
  }
};

function startManualPolling(sessionId) {
  if (manualPollTimer) clearInterval(manualPollTimer);
  let attempts = 0;
  const maxAttempts = 150; // max 5 menit (polling tiap 2 detik)

  const tick = async () => {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(manualPollTimer);
      manualPollTimer = null;
      $("manualLoginStatus").textContent = "⏰ Waktu login habis.";
      $("manualLoginStatus").className = "qr-status-msg expired";
      $("startManualLoginBtn").disabled = false;
      $("startManualLoginBtn").textContent = "Buka Browser Lagi";
      return;
    }

    try {
      const j = await api("/api/shopee/login/manual/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });

      if (j.status === "CONFIRMED" || j.logged_in) {
        clearInterval(manualPollTimer);
        manualPollTimer = null;
        $("manualLoginStatus").textContent = "✅ Login berhasil! Menyimpan cookies...";
        $("manualLoginStatus").className = "qr-status-msg success";
        updateShopeeUI(true);
        setTimeout(() => closeShopeeModal(), 1500);
        toast("Login Shopee berhasil!");
      } else if (j.status === "CANCELLED") {
        clearInterval(manualPollTimer);
        manualPollTimer = null;
        $("manualLoginStatus").textContent = "Jendela browser ditutup.";
        $("manualLoginStatus").className = "qr-status-msg";
        $("startManualLoginBtn").disabled = false;
        $("startManualLoginBtn").textContent = "Buka Browser & Login";
      } else if (j.status === "ERROR") {
        clearInterval(manualPollTimer);
        manualPollTimer = null;
        $("manualLoginStatus").textContent = "❌ " + (j.error || "Gagal login");
        $("manualLoginStatus").className = "qr-status-msg expired";
        $("startManualLoginBtn").disabled = false;
        $("startManualLoginBtn").textContent = "Buka Browser Lagi";
      }
    } catch (e) { /* tunggu tick berikutnya */ }
  };

  manualPollTimer = setInterval(tick, 2000);
}

$("shopeeLogoutBtn").onclick = async () => {
  if (!confirm("Logout dari Shopee?")) return;
  try {
    await api("/api/shopee/logout", { method: "POST" });
    updateShopeeUI(false);
    toast("Berhasil logout Shopee");
  } catch (e) { toast("Gagal logout: " + e.message); }
};

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
  const rawInput = $("productUrl").value.trim();
  if (!rawInput) { errBox("formError", "Link atau teks share produk wajib diisi."); return; }
  
  show("view-preview");
  $("previewLoading").classList.remove("hidden");
  $("previewContent").classList.add("hidden");
  errBox("previewError", "");

  try {
    const j = await api("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: rawInput }),
    });
    state.preview = j.product;
    renderPreview(j.product);
    $("previewLoading").classList.add("hidden");
    $("previewContent").classList.remove("hidden");
    if (j.product && j.product.needs_manual_input) {
      errBox("previewError", "Shopee membatasi akses otomatis. Silakan cek & lengkapi data nama produk di bawah sebelum melanjutkan.");
    }
  } catch (e) {
    $("previewLoading").classList.add("hidden");
    errBox("previewError", e.message + " — Silakan isi data nama produk secara manual di bawah.");
    $("previewContent").classList.remove("hidden");
    renderPreview(null);
  }
};

function renderPreview(main) {
  const p = main || {};
  state.productPhotoFile = null;
  const initialImg = p.image || "";

  $("mainProductCard").innerHTML = `
    <div style="width: 100%; display: flex; flex-direction: column; gap: 12px;">
      <div style="display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap;">
        <div id="previewImgBox" style="width: 130px; height: 130px; border-radius: 10px; border: 2px dashed var(--border); display: flex; align-items: center; justify-content: center; overflow: hidden; background: #fafafa; flex-shrink: 0; cursor: pointer; position: relative;" title="Klik untuk upload foto produk">
          ${initialImg ? `<img id="previewImgEl" src="${initialImg}" style="width: 100%; height: 100%; object-fit: cover;">` : `<div style="font-size: 0.78rem; color: var(--muted); text-align: center; padding: 6px;">📷 Upload Foto Produk</div>`}
        </div>
        <div style="flex: 1; min-width: 240px;">
          <label style="margin: 0 0 4px 0; font-size: 0.88rem;">Nama / Judul Produk <span class="req">*</span></label>
          <input type="text" id="editProductTitle" value="${(p.title || '').replace(/"/g, '&quot;')}" placeholder="Contoh: Xavire Dress Party Dress..." style="margin-bottom: 8px; font-weight: 600;">
          
          <label style="margin: 0 0 4px 0; font-size: 0.88rem;">Harga Produk</label>
          <input type="text" id="editProductPrice" value="${(p.price || '').replace(/"/g, '&quot;')}" placeholder="Contoh: Rp176.500" style="margin-bottom: 0;">
        </div>
      </div>
      <input type="file" id="editProductPhotoFile" accept="image/*" style="display: none;">
      <small style="color: var(--muted);">💡 Anda dapat mengoreksi nama, harga, atau mengupload foto produk langsung sebelum menekan tombol Proses.</small>
    </div>
  `;

  $("previewImgBox").onclick = () => $("editProductPhotoFile").click();
  $("editProductPhotoFile").onchange = (e) => {
    const file = e.target.files[0];
    if (file) {
      state.productPhotoFile = file;
      const url = URL.createObjectURL(file);
      $("previewImgBox").innerHTML = `<img src="${url}" style="width: 100%; height: 100%; object-fit: cover;">`;
    }
  };

  const supGrid = $("supProducts");
  supGrid.innerHTML = "";
  for (const inp of document.querySelectorAll(".supUrl")) {
    const u = inp.value.trim();
    if (!u) continue;
    try {
      api("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: u }) })
        .then((j) => {
          const sp = j.product || {};
          supGrid.innerHTML += `<div class="product-card"><div><b>${sp.title || u}</b><br><span class="price">${sp.price || ""}</span></div></div>`;
        })
        .catch(() => {
          supGrid.innerHTML += `<div class="product-card"><div><b>Produk Penunjang:</b><br><small>${u}</small></div></div>`;
        });
    } catch (e) { /* ignore */ }
  }
}

$("backBtn").onclick = () => show("view-form");

/* ---------- buat job & proses ---------- */
$("processBtn").onclick = async () => {
  const title = $("editProductTitle") ? $("editProductTitle").value.trim() : "";
  if (!title) {
    errBox("previewError", "Nama produk wajib diisi sebelum melanjutkan.");
    return;
  }
  const price = $("editProductPrice") ? $("editProductPrice").value.trim() : "";

  const fd = new FormData();
  fd.append("mode", state.mode);

  // Ambil URL produk yang valid
  let rawUrl = $("productUrl").value.trim();
  let m = rawUrl.match(/(https?:\/\/(?:s\.shopee\.co\.id|shope\.ee|shopee\.co\.id)\/\S+)/);
  let finalUrl = m ? m[1] : (state.preview && state.preview.url ? state.preview.url : rawUrl);
  fd.append("product_url", finalUrl);

  document.querySelectorAll(".supUrl").forEach((i) => { if (i.value.trim()) fd.append("supporting_urls", i.value.trim()); });
  fd.append("character_id", $("characterSelect").value);
  if ($("placePhoto").files[0]) fd.append("place_photo", $("placePhoto").files[0]);

  fd.append("product_title", title);
  fd.append("product_price", price);

  // Jika user mengupload foto produk sendiri, kirimkan file
  if (state.productPhotoFile) {
    fd.append("product_photo", state.productPhotoFile);
  } else if (state.preview && state.preview.image) {
    fd.append("product_image", state.preview.image);
  }

  $("processBtn").disabled = true;
  try {
    const j = await api("/api/jobs", { method: "POST", body: fd });
    state.jobId = j.job_id;
    show("view-process");
    startPolling(j.job_id);
  } catch (e) {
    errBox("previewError", e.message);
  } finally {
    $("processBtn").disabled = false;
  }
};

/* ---------- polling proses ---------- */
function startPolling(jobId) {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.lastLogId = 0;
  $("retryBtn").classList.add("hidden");
  $("newJobBtn").classList.add("hidden");

  const tick = async () => {
    try {
      const [jJob, jLogs] = await Promise.all([api(`/api/jobs/${jobId}`), api(`/api/jobs/${jobId}/logs?since=${state.lastLogId}`)]);
      const job = jJob.job;
      $("progressFill").style.width = `${job.progress || 0}%`;
      $("progressPct").textContent = `${job.progress || 0}%`;
      $("processSub").textContent = job.status === "antrean" ? "Menunggu giliran…" : job.status;

      // checklist
      const ul = $("checklist"); ul.innerHTML = "";
      STAGES.forEach((name, idx) => {
        const step = idx + 1;
        const li = document.createElement("li");
        if (step < job.current_stage || job.status === "story board ready") li.className = "done";
        else if (step === job.current_stage) li.className = "current";
        li.textContent = `${step}. ${name}`;
        ul.appendChild(li);
      });

      // logs
      const panel = $("logPanel");
      (jLogs.logs || []).forEach((l) => {
        state.lastLogId = Math.max(state.lastLogId, l.id);
        const p = document.createElement("p");
        p.className = `log-${l.level || "info"}`;
        p.textContent = `[${l.ts.slice(11, 19)}] ${l.message}`;
        panel.appendChild(p);
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
checkShopeeStatus();
