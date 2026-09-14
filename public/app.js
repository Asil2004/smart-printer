// ----------------- ELEMENTLAR VA HOLATLAR -----------------
let PRICE_BW = 500;
let PRICE_COLOR = 1500;
let detectedPages = 1;

const statusBadge = document.getElementById('statusBadge');
const settingsBtn = document.getElementById('settingsBtn');
const printForm = document.getElementById('printForm');
const fileInput = document.getElementById('fileInput');
const dropZone = document.getElementById('dropZone');
const promptContent = document.getElementById('promptContent');
const fileInfoBox = document.getElementById('fileInfoBox');
const fileNameTxt = document.getElementById('fileNameTxt');
const fileSizeTxt = document.getElementById('fileSizeTxt');
const filePagesTxt = document.getElementById('filePagesTxt');
const fileTypeIcon = document.getElementById('fileTypeIcon');
const removeFileBtn = document.getElementById('removeFileBtn');
const printSubmitBtn = document.getElementById('printSubmitBtn');

// Sozlamalar
const copiesVal = document.getElementById('copiesVal');
const plusCopyBtn = document.getElementById('plusCopyBtn');
const minusCopyBtn = document.getElementById('minusCopyBtn');
const pageRangesInput = document.getElementById('pageRangesInput');

// Kalkulyator
const calcPagesCount = document.getElementById('calcPagesCount');
const calcCopiesCount = document.getElementById('calcCopiesCount');
const calcSheetsCount = document.getElementById('calcSheetsCount');
const totalPriceTxt = document.getElementById('totalPriceTxt');


// ----------------- BACKEND ALOQASINI TEKSHIRISH -----------------
async function checkBackendHealth() {
  const apiUrl = AppConfig.getApiUrl();
  
  if (!apiUrl) {
    statusBadge.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-rose-500 inline-block"></span>
      <span class="text-rose-600 font-semibold cursor-pointer" onclick="openSettingsModal()">Server URL kiritilmagan</span>
    `;
    return false;
  }

  try {
    statusBadge.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-amber-500 inline-block animate-pulse"></span>
      <span>Tekshirilmoqda...</span>
    `;

    const res = await fetch(`${apiUrl}/api/health`, {
      method: "GET",
      headers: { "ngrok-skip-browser-warning": "true" }
    });
    const data = await res.json();

    if (data.status === "online") {
      PRICE_BW = data.price_bw || 500;
      PRICE_COLOR = data.price_color || 1500;
      statusBadge.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse"></span>
        <span class="text-emerald-700 font-semibold truncate max-w-[140px]">${data.printer || "Printer tayyor"}</span>
      `;
      updatePricing();
      return true;
    }
  } catch (err) {
    statusBadge.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-rose-500 inline-block"></span>
      <span class="text-rose-600 font-semibold cursor-pointer" onclick="openSettingsModal()">Terminal oflayn</span>
    `;
  }
  return false;
}


// ----------------- SOZLAMALAR MODALI (SETTINGS) -----------------
function openSettingsModal() {
  const currentUrl = AppConfig.getApiUrl();

  Swal.fire({
    title: "Terminal Sozlamalari",
    html: `
      <div class="text-left text-xs text-slate-600 space-y-3">
        <p>Raspberry Pi dagi Cloudflare Tunnel yoki Server API manzilini kiriting:</p>
        <input id="swalApiUrlInput" class="swal2-input !text-xs !w-full !m-0 !box-border" placeholder="Masalan: https://printchi-api.loca.lt yoki https://xxx.trycloudflare.com" value="${currentUrl}">
        <p class="text-[11px] text-slate-400 leading-relaxed">
          * Maslahat: Raspberry Pi da <code>cloudflared tunnel</code> yoki <code>ngrok</code> buyrug'i orqali bepul olingan HTTPS manzilini kiriting.
        </p>
      </div>
    `,
    showCancelButton: true,
    confirmButtonColor: "#2563eb",
    cancelButtonColor: "#64748b",
    confirmButtonText: "Saqlash va Tekshirish",
    cancelButtonText: "Bekor qilish",
    preConfirm: () => {
      const input = document.getElementById("swalApiUrlInput").value.trim();
      return input;
    }
  }).then((result) => {
    if (result.isConfirmed) {
      AppConfig.setApiUrl(result.value);
      checkBackendHealth();
    }
  });
}

settingsBtn.addEventListener("click", openSettingsModal);


// ----------------- FAYL VA KALKULYATOR MANTIG'I -----------------
function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function updatePricing() {
  const copies = parseInt(copiesVal.value) || 1;
  const colorMode = document.querySelector('input[name="color_mode"]:checked').value;
  const duplex = document.querySelector('input[name="duplex"]:checked').value;

  let pages = detectedPages;
  const rangeStr = pageRangesInput.value.trim();
  if (rangeStr && rangeStr.includes("-")) {
    const parts = rangeStr.split("-");
    const p1 = parseInt(parts[0]);
    const p2 = parseInt(parts[1]);
    if (!isNaN(p1) && !isNaN(p2) && p2 >= p1) {
      pages = p2 - p1 + 1;
    }
  }

  const totalImpressions = pages * copies;
  const unitPrice = (colorMode === "color") ? PRICE_COLOR : PRICE_BW;
  const totalPrice = totalImpressions * unitPrice;

  let sheets = totalImpressions;
  if (duplex === "two-sided") {
    sheets = Math.ceil(pages / 2) * copies;
  }

  calcPagesCount.textContent = pages;
  calcCopiesCount.textContent = copies;
  calcSheetsCount.textContent = sheets + " varaq";
  totalPriceTxt.textContent = totalPrice.toLocaleString();
}

plusCopyBtn.addEventListener("click", () => {
  let val = parseInt(copiesVal.value) || 1;
  if (val < 10) copiesVal.value = val + 1;
  updatePricing();
});

minusCopyBtn.addEventListener("click", () => {
  let val = parseInt(copiesVal.value) || 1;
  if (val > 1) copiesVal.value = val - 1;
  updatePricing();
});

document.querySelectorAll('input[name="color_mode"], input[name="duplex"]').forEach((el) => {
  el.addEventListener("change", updatePricing);
});
pageRangesInput.addEventListener("input", updatePricing);


// ----------------- FAYL TANLASH -----------------
async function handleSelectedFile(file) {
  if (!file) return;

  fileNameTxt.textContent = file.name;
  fileSizeTxt.textContent = formatBytes(file.size);
  filePagesTxt.textContent = "Sahifalar sanalmoqda...";

  const ext = file.name.split(".").pop().toLowerCase();
  if (ext === "pdf") {
    fileTypeIcon.className = "fa-solid fa-file-pdf text-rose-500";
  } else if (ext === "docx") {
    fileTypeIcon.className = "fa-solid fa-file-word text-blue-500";
  } else if (["png", "jpg", "jpeg"].includes(ext)) {
    fileTypeIcon.className = "fa-solid fa-file-image text-emerald-500";
  } else {
    fileTypeIcon.className = "fa-solid fa-file text-slate-500";
  }

  promptContent.classList.add("hidden");
  fileInfoBox.classList.remove("hidden");

  // 1. Agar PDF bo'lsa - Mozilla PDF.js orqali brauzerning o'zida bir zumda (instant) sahifalarni sanash
  if (ext === "pdf" && window.pdfjsLib) {
    try {
      const arrayBuffer = await file.arrayBuffer();
      const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
      detectedPages = Math.max(1, pdf.numPages || 1);
      filePagesTxt.textContent = `${detectedPages} ta sahifa`;
      updatePricing();
      return;
    } catch (pdfErr) {
      console.warn("PDF.js tahlil xatosi, server API orqali tekshirilmoqda:", pdfErr);
    }
  }

  // 2. Agar DOCX bo'lsa yoki PDF server orqali tekshirilsa
  const apiUrl = AppConfig.getApiUrl();
  if (apiUrl && (ext === "pdf" || ext === "docx")) {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${apiUrl}/api/inspect-file`, { method: "POST", body: fd });
      const data = await res.json();
      if (data.success && data.page_count) {
        detectedPages = Math.max(1, data.page_count);
        filePagesTxt.textContent = `${detectedPages} ta sahifa`;
      } else {
        detectedPages = 1;
        filePagesTxt.textContent = "1 ta sahifa";
      }
    } catch (e) {
      detectedPages = 1;
      filePagesTxt.textContent = "1 ta sahifa";
    }
  } else {
    detectedPages = 1;
    filePagesTxt.textContent = "1 ta sahifa";
  }

  updatePricing();
}

fileInput.addEventListener("change", (e) => {
  if (e.target.files.length > 0) {
    handleSelectedFile(e.target.files[0]);
  }
});

removeFileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  fileInput.value = "";
  fileInfoBox.classList.add("hidden");
  promptContent.classList.remove("hidden");
  detectedPages = 1;
  updatePricing();
});

// Drag & Drop
["dragenter", "dragover"].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add("border-blue-500", "bg-blue-50/50");
  });
});
["dragleave", "drop"].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove("border-blue-500", "bg-blue-50/50");
  });
});
dropZone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length > 0) {
    fileInput.files = e.dataTransfer.files;
    handleSelectedFile(e.dataTransfer.files[0]);
  }
});


// ----------------- FORM YUBORISH (PRINT) -----------------
printForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  if (!fileInput.files.length) {
    Swal.fire({
      icon: "warning",
      title: "Fayl tanlanmadi!",
      text: "Iltimos, avval chop etilishi kerak bo'lgan hujjatni yuklang.",
      confirmButtonColor: "#2563eb",
      confirmButtonText: "Tushundim"
    });
    return;
  }

  const apiUrl = AppConfig.getApiUrl();
  if (!apiUrl) {
    Swal.fire({
      icon: "error",
      title: "Terminal Ulanmagan!",
      text: "Raspberry Pi terminalining API manzili o'rnatilmagan. Sozlamalar (⚙️) orqali manzilni kiriting.",
      confirmButtonColor: "#2563eb",
      confirmButtonText: "Sozlash"
    }).then(openSettingsModal);
    return;
  }

  // Modal ko'rsatish
  Swal.fire({
    title: "Chop etilmoqda...",
    html: `
      <div class="space-y-3 py-2 text-center">
        <div class="text-xs text-slate-500" id="swalStepText">Fayl serverga yuklanmoqda...</div>
        <div class="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
          <div id="swalBar" class="bg-blue-600 h-full rounded-full transition-all duration-500" style="width: 30%"></div>
        </div>
      </div>
    `,
    allowOutsideClick: false,
    allowEscapeKey: false,
    showConfirmButton: false,
    didOpen: () => {
      Swal.showLoading();
    }
  });

  const formData = new FormData(printForm);

  try {
    setTimeout(() => {
      const stepText = document.getElementById("swalStepText");
      const bar = document.getElementById("swalBar");
      if (stepText && bar) {
        stepText.textContent = "Hujjat printer formatiga moslashtirilmoqda...";
        bar.style.width = "75%";
      }
    }, 1000);

    const res = await fetch(`${apiUrl}/api/print`, {
      method: "POST",
      headers: { "ngrok-skip-browser-warning": "true" },
      body: formData
    });
    const result = await res.json();

    if (res.ok && result.success) {
      const bar = document.getElementById("swalBar");
      if (bar) bar.style.width = "100%";

      Swal.fire({
        icon: "success",
        title: "Muvaffaqiyatli!",
        html: `
          <div class="text-sm text-slate-600 space-y-2">
            <p>${result.message}</p>
            <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-700 text-left">
              <div><strong>Printer:</strong> ${result.printer}</div>
              <div><strong>Nusxalar soni:</strong> ${result.copies} ta</div>
            </div>
          </div>
        `,
        confirmButtonColor: "#16a34a",
        confirmButtonText: "Ajoyib, tushundim"
      });

      printForm.reset();
      fileInfoBox.classList.add("hidden");
      promptContent.classList.remove("hidden");
      detectedPages = 1;
      updatePricing();
    } else {
      Swal.fire({
        icon: "error",
        title: "Xatolik!",
        text: result.message || "Printerga yuborishda xatolik yuz berdi.",
        confirmButtonColor: "#e11d48",
        confirmButtonText: "Qayta urinish"
      });
    }
  } catch (err) {
    Swal.fire({
      icon: "error",
      title: "Aloqa uzildi!",
      text: "Raspberry Pi terminali bilan bog'lanib bo'lmadi. Terminal yoqilganligini tekshiring.",
      confirmButtonColor: "#e11d48",
      confirmButtonText: "Yopish"
    });
  }
});

// Boshlang'ich tekshiruv va hisob
updatePricing();
checkBackendHealth();
