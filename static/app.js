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

/* ========== Shopee QR Login ========== */
let qrPollTimer = null;
let qrCountdownTimer = null;
let currentQrId = null;

async function checkShopeeStatus() {
  try {
    const j = await api("/api/shopee/status");
    updateShopeeUI(j.logged_in);
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

$("shopeeLoginBtn").onclick = async () => {
  $("qrModal").classList.remove("hidden");
  await loadQR();
};

$("qrCloseBtn").onclick = () => closeQRModal();
$("qrModal").onclick = (e) => { if (e.target === $("qrModal")) closeQRModal(); };

function closeQRModal() {
  $("qrModal").classList.add("hidden");
  if (qrPollTimer) { clearInterval(qrPollTimer); qrPollTimer = null; }
  if (qrCountdownTimer) { clearInterval(qrCountdownTimer); qrCountdownTimer = null; }
  if (currentQrId) {
    api("/api/shopee/qr/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ qrcode_id: currentQrId }),
    }).catch(() => {});
    currentQrId = null;
  }
}

$("qrRefreshBtn").onclick = async () => {
  if (qrPollTimer) { clearInterval(qrPollTimer); qrPollTimer = null; }
  if (qrCountdownTimer) { clearInterval(qrCountdownTimer); qrCountdownTimer = null; }
  await loadQR();
};

async function loadQR() {
  $("qrLoading").classList.remove("hidden");
  $("qrLoading").textContent = "Memuat QR Code...";
  $("qrImageWrap").classList.add("hidden");
  $("qrTimer").classList.add("hidden");
  $("qrInstruction").classList.add("hidden");
  $("qrRefreshBtn").classList.add("hidden");
  $("qrStatusMsg").textContent = "";
  $("qrStatusMsg").className = "qr-status-msg";

  if (qrCountdownTimer) { clearInterval(qrCountdownTimer); qrCountdownTimer = null; }

  try {
    const j = await api("/api/shopee/qr", { method: "POST" });
    if (!j.ok) throw new Error(j.error || "Gagal generate QR");

    currentQrId = j.qrcode_id;
    $("qrImage").src = "data:image/png;base64," + j.qrcode_base64;
    $("qrLoading").classList.add("hidden");
    $("qrImageWrap").classList.remove("hidden");
    $("qrTimer").classList.remove("hidden");
    $("qrInstruction").classList.remove("hidden");

    // Countdown 60 detik
    let timeLeft = 60;
    $("qrTimerCount").textContent = timeLeft;
    qrCountdownTimer = setInterval(() => {
      timeLeft--;
      if (timeLeft <= 0) {
        clearInterval(qrCountdownTimer);
        qrCountdownTimer = null;
        $("qrTimer").classList.add("hidden");
        $("qrStatusMsg").textContent = "⏰ QR Code kedaluwarsa. Silakan buat QR baru.";
        $("qrStatusMsg").className = "qr-status-msg expired";
        $("qrRefreshBtn").classList.remove("hidden");
      } else {
        $("qrTimerCount").textContent = timeLeft;
      }
    }, 1000);

    // Start polling status
    startQRPolling(j.qrcode_id);
  } catch (e) {
    $("qrLoading").textContent = "Gagal memuat QR: " + e.message;
    $("qrRefreshBtn").classList.remove("hidden");
  }
}

function startQRPolling(qrId) {
  if (qrPollTimer) clearInterval(qrPollTimer);
  let attempts = 0;
  const maxAttempts = 60; // polling tiap 2 dtk

  const tick = async () => {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(qrPollTimer);
      qrPollTimer = null;
      if (qrCountdownTimer) { clearInterval(qrCountdownTimer); qrCountdownTimer = null; }
      $("qrStatusMsg").textContent = "⏰ QR Code kedaluwarsa";
      $("qrStatusMsg").className = "qr-status-msg expired";
      $("qrRefreshBtn").classList.remove("hidden");
      return;
    }
    try {
      const j = await api("/api/shopee/qr/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ qrcode_id: qrId }),
      });

      if (j.status === "SCANNED") {
        $("qrStatusMsg").textContent = "📱 QR di-scan! Konfirmasi di HP Anda...";
        $("qrStatusMsg").className = "qr-status-msg scanning";
      } else if (j.status === "CONFIRMED") {
        clearInterval(qrPollTimer);
        qrPollTimer = null;
        if (qrCountdownTimer) { clearInterval(qrCountdownTimer); qrCountdownTimer = null; }
        $("qrTimer").classList.add("hidden");
        $("qrStatusMsg").textContent = "✅ Login berhasil!";
        $("qrStatusMsg").className = "qr-status-msg success";
        updateShopeeUI(true);
        setTimeout(() => closeQRModal(), 1500);
        toast("Login Shopee berhasil!");
      } else if (j.status === "EXPIRED" || j.status === "ERROR") {
        clearInterval(qrPollTimer);
        qrPollTimer = null;
        if (qrCountdownTimer) { clearInterval(qrCountdownTimer); qrCountdownTimer = null; }
        $("qrTimer").classList.add("hidden");
        $("qrStatusMsg").textContent = "⏰ " + (j.error || "QR Code kedaluwarsa");
        $("qrStatusMsg").className = "qr-status-msg expired";
        $("qrRefreshBtn").classList.remove("hidden");
      }
    } catch (e) { /* tunggu tick berikutnya */ }
  };

  tick();
  qrPollTimer = setInterval(tick, 2000);
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

  if (state.productPhotoFile) {
    fd.append("product_photo", state.productPhotoFile);
  } else if (state.preview && state.preview.image) {
    fd.append("product_image", state.preview.image);
  }

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
checkShopeeStatus();
