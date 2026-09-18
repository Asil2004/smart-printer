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

// ----------------- TAB NAVIGATSIYA -----------------
function switchTab(tab) {
  ['print', 'templates', 'ai'].forEach(t => {
    const sec = document.getElementById(`section-${t}`);
    const btn = document.getElementById(`tab-${t}`);
    if (!sec || !btn) return;
    if (t === tab) {
      sec.classList.remove('hidden');
      btn.classList.add('bg-blue-600', 'text-white', 'shadow-sm');
      btn.classList.remove('text-slate-500');
    } else {
      sec.classList.add('hidden');
      btn.classList.remove('bg-blue-600', 'text-white', 'shadow-sm');
      btn.classList.add('text-slate-500');
    }
  });
  if (tab === 'templates') loadTemplates();
}

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
      loadPrinterStatus();
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
  const payCfg = AppConfig.getPaymentConfig();

  Swal.fire({
    title: "Tizim va To‘lov Sozlamalari",
    html: `
      <div class="text-left text-xs text-slate-600 space-y-3">
        <div>
          <label class="font-bold text-slate-700 block mb-1">Raspberry Pi API Manzili:</label>
          <input id="swalApiUrlInput" class="swal2-input !text-xs !w-full !m-0 !box-border" placeholder="https://snazzy-chosen-lyricism.ngrok-free.dev" value="${currentUrl}">
        </div>
        <div class="pt-2 border-t border-slate-100">
          <label class="font-bold text-slate-700 block mb-1">To‘lov Karta Raqami (Uzcard / Humo):</label>
          <input id="swalCardNumberInput" class="swal2-input !text-xs !w-full !m-0 !box-border" placeholder="8600 0000 0000 0000" value="${payCfg.cardNumber || ''}">
        </div>
        <div>
          <label class="font-bold text-slate-700 block mb-1">Karta Egasi Ism-Familiyasi:</label>
          <input id="swalCardHolderInput" class="swal2-input !text-xs !w-full !m-0 !box-border" placeholder="F.I.SH." value="${payCfg.cardHolder || ''}">
        </div>
        <div>
          <label class="font-bold text-slate-700 block mb-1">Click / Payme Telefon Raqami:</label>
          <input id="swalPhoneInput" class="swal2-input !text-xs !w-full !m-0 !box-border" placeholder="+998901234567" value="${payCfg.clickPhone || ''}">
        </div>
      </div>
    `,
    showCancelButton: true,
    confirmButtonColor: "#2563eb",
    cancelButtonColor: "#64748b",
    confirmButtonText: "Saqlash",
    cancelButtonText: "Bekor qilish",
    preConfirm: () => {
      return {
        apiUrl: document.getElementById("swalApiUrlInput").value.trim(),
        cardNumber: document.getElementById("swalCardNumberInput").value.trim(),
        cardHolder: document.getElementById("swalCardHolderInput").value.trim(),
        phone: document.getElementById("swalPhoneInput").value.trim()
      };
    }
  }).then((result) => {
    if (result.isConfirmed) {
      const data = result.value;
      AppConfig.setApiUrl(data.apiUrl);
      const updatedCfg = {
        ...payCfg,
        cardNumber: data.cardNumber || payCfg.cardNumber,
        cardHolder: data.cardHolder || payCfg.cardHolder,
        clickPhone: data.phone || payCfg.clickPhone,
        paymePhone: data.phone || payCfg.paymePhone
      };
      AppConfig.setPaymentConfig(updatedCfg);
      checkBackendHealth();
      Swal.fire({
        icon: "success",
        title: "Saqlandi!",
        text: "Barcha sozlamalar muvaffaqiyatli yangilandi.",
        timer: 1500,
        showConfirmButton: false
      });
    }
  });
}

if (settingsBtn) settingsBtn.addEventListener("click", openSettingsModal);

// ----------------- PRINTER STATUS PANELI -----------------
const PRINTER_ICONS = {
  thermal:  { icon: 'fa-receipt',   color: 'text-amber-500',  bg: 'bg-amber-50'  },
  laser_bw: { icon: 'fa-print',     color: 'text-slate-600',  bg: 'bg-slate-50'  },
  color:    { icon: 'fa-palette',   color: 'text-pink-500',   bg: 'bg-pink-50'   },
};

async function loadPrinterStatus() {
  const list = document.getElementById('printerStatusList');
  if (!list) return;
  const apiUrl = AppConfig.getApiUrl();
  if (!apiUrl) return;

  try {
    const res = await fetch(`${apiUrl}/api/printers`, {
      headers: { "ngrok-skip-browser-warning": "true" }
    });
    const data = await res.json();
    if (!data.success) throw new Error('API xatosi');

    list.innerHTML = data.printers.map(p => {
      const meta = PRINTER_ICONS[p.type] || { icon: 'fa-print', color: 'text-slate-400', bg: 'bg-slate-50' };
      const dot  = p.connected
        ? '<span class="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse flex-shrink-0"></span>'
        : '<span class="w-2 h-2 rounded-full bg-slate-300 inline-block flex-shrink-0"></span>';
      const nameText = p.connected
        ? `<span class="font-semibold text-slate-800">${p.cups_name || p.label}</span>`
        : `<span class="text-slate-400">${p.label}</span>`;
      const stateText = p.connected
        ? '<span class="text-[10px] text-emerald-600 font-medium">Ulangan</span>'
        : '<span class="text-[10px] text-slate-400">Ulanmagan</span>';
      return `<div class="flex items-center gap-3 px-3 py-2 rounded-xl ${p.connected ? 'bg-emerald-50/60 border border-emerald-100' : 'bg-slate-50 border border-slate-100'}">
        <div class="w-8 h-8 rounded-lg ${meta.bg} flex items-center justify-center flex-shrink-0">
          <i class="fa-solid ${meta.icon} text-sm ${meta.color}"></i>
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-xs flex items-center gap-1.5">${dot} ${nameText}</div>
          <div class="mt-0.5">${stateText}</div>
        </div>
      </div>`;
    }).join('');
    updateRoutingHint();
  } catch (e) {
    list.innerHTML = '<div class="text-xs text-slate-400 text-center py-2">Printerlar holatini olib bo\'lmadi</div>';
  }
}

function updateRoutingHint() {
  const colorMode = document.querySelector('input[name="color_mode"]:checked')?.value || 'gray';
  const hintEl    = document.getElementById('routingHint');
  const hintText  = document.getElementById('routingHintText');
  if (!hintEl || !hintText) return;
  const HINTS = {
    gray:  'Oq-qora → Canon lazer printerga yuboriladi',
    color: 'Rangli  → Rangli printerga yuboriladi'
  };
  hintText.textContent = HINTS[colorMode] || '';
  hintEl.classList.remove('hidden');
}

document.querySelectorAll('input[name="color_mode"]').forEach(r => {
  r.addEventListener('change', updateRoutingHint);
});

// ----------------- FAYL VA KALKULYATOR MANTIG'I -----------------
function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

async function detectPdfPages(file) {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    return pdf.numPages || 1;
  } catch (e) {
    console.warn("PDF.js orqali sahifalarni o'qishda xatolik:", e);
    return 1;
  }
}

function parsePageRanges(rangeStr, totalPages) {
  if (!rangeStr || !rangeStr.trim()) return totalPages;
  const parts = rangeStr.split(",");
  let count = 0;
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.includes("-")) {
      const [start, end] = trimmed.split("-").map(n => parseInt(n.trim(), 10));
      if (!isNaN(start) && !isNaN(end)) {
        count += Math.max(0, Math.min(end, totalPages) - Math.max(1, start) + 1);
      }
    } else {
      const num = parseInt(trimmed, 10);
      if (!isNaN(num) && num >= 1 && num <= totalPages) {
        count += 1;
      }
    }
  }
  return count > 0 ? count : totalPages;
}

function updatePricing() {
  const colorMode = document.querySelector('input[name="color_mode"]:checked')?.value || 'gray';
  const duplex = document.querySelector('input[name="duplex"]:checked')?.value || 'one-sided';
  const copies = parseInt(copiesVal ? copiesVal.value : 1) || 1;
  const ranges = pageRangesInput ? pageRangesInput.value.trim() : '';

  const effectivePages = parsePageRanges(ranges, detectedPages);
  const pricePerPage = colorMode === 'color' ? PRICE_COLOR : PRICE_BW;
  const totalPrice = effectivePages * copies * pricePerPage;

  let sheets = effectivePages * copies;
  if (duplex === 'two-sided') {
    sheets = Math.ceil(sheets / 2);
  }

  if (calcPagesCount) calcPagesCount.textContent = effectivePages;
  if (calcCopiesCount) calcCopiesCount.textContent = copies;
  if (calcSheetsCount) calcSheetsCount.textContent = `${sheets} varaq`;
  if (totalPriceTxt) totalPriceTxt.textContent = totalPrice.toLocaleString();
}

// Fayl tanlash
if (fileInput) {
  fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    fileNameTxt.textContent = file.name;
    fileSizeTxt.textContent = formatBytes(file.size);

    const ext = file.name.split('.').pop().toLowerCase();
    if (ext === 'pdf') {
      fileTypeIcon.className = 'fa-solid fa-file-pdf';
      filePagesTxt.textContent = 'Sahifalar sanalmoqda...';
      detectedPages = await detectPdfPages(file);
      filePagesTxt.textContent = `${detectedPages} sahifa`;
    } else if (ext === 'docx') {
      fileTypeIcon.className = 'fa-solid fa-file-word';
      detectedPages = 1;
      filePagesTxt.textContent = 'Word hujjati';
    } else if (['jpg', 'jpeg', 'png'].includes(ext)) {
      fileTypeIcon.className = 'fa-solid fa-file-image';
      detectedPages = 1;
      filePagesTxt.textContent = '1 sahifa (Rasm)';
    } else {
      fileTypeIcon.className = 'fa-solid fa-file';
      detectedPages = 1;
      filePagesTxt.textContent = '1 sahifa';
    }

    promptContent.classList.add('hidden');
    fileInfoBox.classList.remove('hidden');
    updatePricing();
  });
}

if (removeFileBtn) {
  removeFileBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.value = '';
    fileInfoBox.classList.add('hidden');
    promptContent.classList.remove('hidden');
    detectedPages = 1;
    updatePricing();
  });
}

// Nusxa tugmalari
if (plusCopyBtn) {
  plusCopyBtn.addEventListener('click', () => {
    let c = parseInt(copiesVal.value) || 1;
    if (c < 10) copiesVal.value = c + 1;
    updatePricing();
  });
}

if (minusCopyBtn) {
  minusCopyBtn.addEventListener('click', () => {
    let c = parseInt(copiesVal.value) || 1;
    if (c > 1) copiesVal.value = c - 1;
    updatePricing();
  });
}

if (pageRangesInput) pageRangesInput.addEventListener('input', updatePricing);
document.querySelectorAll('input[name="color_mode"], input[name="duplex"]').forEach(input => {
  input.addEventListener('change', updatePricing);
});

// ----------------- SHABLONLAR -----------------
let allTemplates = [];
let selectedTemplate = null;

async function loadTemplates() {
  const apiUrl = AppConfig.getApiUrl();
  const grid = document.getElementById('templateGrid');
  if (!grid || !apiUrl) return;

  if (allTemplates.length > 0) { renderTemplates(allTemplates); return; }
  try {
    const res = await fetch(`${apiUrl}/api/templates`, {
      headers: { "ngrok-skip-browser-warning": "true" }
    });
    const data = await res.json();
    allTemplates = data.templates || [];
    renderTemplates(allTemplates);
  } catch (e) {
    grid.innerHTML = '<div class="col-span-2 text-center text-xs text-rose-400 py-6">Shablonlar yuklanmadi</div>';
  }
}

function renderTemplates(list) {
  const grid = document.getElementById('templateGrid');
  if (!grid) return;
  if (!list.length) {
    grid.innerHTML = '<div class="col-span-2 text-center text-xs text-slate-400 py-6">Shablonlar topilmadi</div>';
    return;
  }
  grid.innerHTML = list.map(t => `
    <div onclick="openTemplateModal(${JSON.stringify(t).replace(/"/g, '&quot;')})"
      class="bg-white rounded-2xl border border-slate-200 p-3 shadow-sm cursor-pointer hover:border-blue-400 hover:shadow-md transition-all active:scale-95">
      <div class="w-10 h-10 rounded-xl ${t.color ? 'bg-pink-50' : 'bg-blue-50'} flex items-center justify-center mb-2">
        <i class="fa-solid fa-file-pdf text-xl ${t.color ? 'text-pink-500' : 'text-blue-500'}"></i>
      </div>
      <div class="text-xs font-bold text-slate-800 leading-tight mb-0.5">${t.name}</div>
      <div class="text-[10px] text-slate-400 leading-tight mb-2 line-clamp-2">${t.description}</div>
      <div class="flex items-center justify-between">
        <span class="text-[11px] font-bold text-blue-600">${t.price_per_page.toLocaleString()} so'm</span>
        ${t.file_exists
          ? '<span class="text-[10px] text-emerald-600 font-medium">✓ Mavjud</span>'
          : '<span class="text-[10px] text-slate-400">Fayl yo\'q</span>'}
      </div>
    </div>`).join('');
}

function filterTemplates(cat) {
  document.querySelectorAll('.filter-btn').forEach(b => {
    b.classList.remove('bg-blue-600', 'text-white');
    b.classList.add('text-slate-500');
  });
  const activeId = cat ? `filter-${cat}` : 'filter-all';
  const activeBtn = document.getElementById(activeId);
  if (activeBtn) {
    activeBtn.classList.add('bg-blue-600', 'text-white');
    activeBtn.classList.remove('text-slate-500');
  }
  const filtered = cat ? allTemplates.filter(t => t.category === cat) : allTemplates;
  renderTemplates(filtered);
}

function openTemplateModal(tmpl) {
  selectedTemplate = tmpl;
  document.getElementById('tmplModalName').textContent = tmpl.name;
  document.getElementById('tmplModalDesc').textContent = tmpl.description;
  document.getElementById('tmplModalPrice').textContent = `${tmpl.price_per_page.toLocaleString()} so'm/bet`;
  const m = document.getElementById('templateModal');
  m.classList.remove('hidden');
  m.style.display = 'flex';
  document.getElementById('tmplPrintBtn').onclick = () => printTemplate(tmpl);
  document.getElementById('tmplDeleteBtn').onclick = () => deleteTemplate(tmpl);
}

function closeTemplateModal() {
  const m = document.getElementById('templateModal');
  m.classList.add('hidden');
  m.style.display = 'none';
}

async function deleteTemplate(tmpl) {
  closeTemplateModal();
  const confirmed = await Swal.fire({
    icon: 'warning',
    title: "O'chirishni tasdiqlang",
    text: `"${tmpl.name}" shabloni o'chiriladi!`,
    showCancelButton: true,
    confirmButtonColor: '#e11d48',
    cancelButtonText: 'Bekor',
    confirmButtonText: "Ha, o'chir"
  });
  if (!confirmed.isConfirmed) return;

  const apiUrl = AppConfig.getApiUrl();
  try {
    const res = await fetch(`${apiUrl}/api/admin/templates/delete/${tmpl.id}`, {
      method: 'DELETE',
      headers: { "ngrok-skip-browser-warning": "true" }
    });
    const data = await res.json();
    allTemplates = [];
    loadTemplates();
    Swal.fire({ icon: data.success ? 'success' : 'error', title: data.message, timer: 2000, showConfirmButton: false });
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'Xatolik', text: 'Server bilan bog\'lanishda xatolik' });
  }
}

function openAdminUpload() {
  document.getElementById('adminUploadModal').classList.remove('hidden');
}
function closeAdminUpload() {
  document.getElementById('adminUploadModal').classList.add('hidden');
  document.getElementById('adminUploadForm').reset();
  document.getElementById('adminFileName').textContent = 'PDF yoki DOCX tanlang';
}

document.getElementById('adminFileInput')?.addEventListener('change', function() {
  const nameEl = document.getElementById('adminFileName');
  if (this.files[0]) {
    nameEl.textContent = '📎 ' + this.files[0].name;
    nameEl.classList.add('text-emerald-600');
    const autoName = this.files[0].name.replace(/\.(pdf|docx)$/i, '').replace(/_/g, ' ');
    const nameInput = document.getElementById('adminTmplName');
    if (!nameInput.value) nameInput.value = autoName;
  }
});

document.getElementById('adminUploadForm')?.addEventListener('submit', async function(e) {
  e.preventDefault();
  const btn = document.getElementById('adminUploadBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i>Yuklanmoqda...';

  const formData = new FormData(this);
  if (!formData.get('color')) formData.set('color', 'false');

  const apiUrl = AppConfig.getApiUrl();
  try {
    const res = await fetch(`${apiUrl}/api/admin/templates/upload`, {
      method: 'POST',
      headers: { "ngrok-skip-browser-warning": "true" },
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      closeAdminUpload();
      allTemplates = [];
      loadTemplates();
      Swal.fire({ icon: 'success', title: data.message, timer: 2500, showConfirmButton: false });
    } else {
      Swal.fire({ icon: 'error', title: 'Xatolik', text: data.message, confirmButtonColor: '#e11d48' });
    }
  } catch (err) {
    Swal.fire({ icon: 'error', title: 'Aloqa xatosi', text: 'Server bilan bog\'lanishda xatolik' });
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-upload mr-1"></i>Yuklash';
  }
});

async function printTemplate(tmpl) {
  if (!tmpl.file_exists) {
    Swal.fire({
      icon: 'warning',
      title: 'Fayl topilmadi',
      text: `"${tmpl.file}" fayli serverda topilmadi.`,
      confirmButtonColor: '#e11d48'
    });
    return;
  }
  closeTemplateModal();
  Swal.fire({ title: 'Chop etilmoqda...', allowOutsideClick: false, didOpen: () => Swal.showLoading() });

  const apiUrl = AppConfig.getApiUrl();
  try {
    const res = await fetch(`${apiUrl}/api/templates/print`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        "ngrok-skip-browser-warning": "true"
      },
      body: JSON.stringify({ template_id: tmpl.id, copies: 1, payment_method: 'card', amount: tmpl.price_per_page })
    });
    const data = await res.json();
    Swal.fire({
      icon: data.success ? 'success' : 'error',
      title: data.success ? 'Chop etildi!' : 'Xatolik',
      text: data.message,
      confirmButtonColor: data.success ? '#2563eb' : '#e11d48'
    });
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'Xatolik', text: 'Server bilan bog\'lanishda xatolik', confirmButtonColor: '#e11d48' });
  }
}

// ----------------- AI WRITER (CLIENT-SIDE & SERVER FALLBACK) -----------------
let currentDocId = null;
let currentGeneratedText = "";

const DOC_TYPE_BASE_PRICES = {
  ariza: 3000,
  dalolatnoma: 4000,
  mustaqil: 5000,
  qayta: 3000,
  xat: 3000
};

function buildClientPrompt(docType, recipient, content, author, org) {
  const today = new Date().toLocaleDateString('ru-RU');
  const base = `Siz O'zbekiston rasmiy hujjatlarini yozishda mutaxassis assistantsiz.
Quyidagi ma'lumotlar asosida rasmiy hujjat yozing (O'zbekiston standartlariga mos, rasmiy uslubda).
MUHIM: Faqat hujjat matnini qaytaring, ortiqcha salomlashish yoki tushuntirish YOZMA. O'zbek tilida yozing. Sana: ${today}.

`;
  if (docType === 'ariza') {
    return base + `ARIZA:
Kimga: ${recipient}
Kim tomonidan: ${author}
Muassasa: ${org || '[muassasa nomi]'}
Mazmun: ${content}

Tuzilishi:
1. Yuqori o'ng burchak: Kimga (lavozim, F.I.O.) va Kimdan
2. Markazda: "ARIZA"
3. Asosiy iltimos / ariza matni
4. Sana va imzo joyi`;
  } else if (docType === 'dalolatnoma') {
    return base + `DALOLATNOMA:
Tashkilot: ${org || '[tashkilot nomi]'}
Ishtirokchilar: ${recipient}
Voqea/Holat: ${content}
Komissiya a'zolari, aniqlangan faktlar, xulosa va imzolar bilan to'liq dalolatnoma yozing.`;
  } else if (docType === 'mustaqil') {
    return base + `MUSTAQIL ISH:
Mavzu: ${content}
Talaba: ${author}
Fan: ${recipient}
Muassasa: ${org || '[universitet nomi]'}
Kirish, asosiy qismlar, xulosa va adabiyotlar bilan ilmiy uslubda mustaqil ish yozing.`;
  } else if (docType === 'qayta') {
    return base + `QAYTA O'ZLASHTIRISH ARIZASI:
Kimga: ${recipient}
Talaba: ${author}
Muassasa: ${org || '[universitet nomi]'}
Sabab: ${content}
Qayta o'zlashtirish imtihoniga ruxsat so'rab to'liq ariza yozing.`;
  } else {
    return base + `RASMIY XAT:
Kimga: ${recipient}
Kimdan: ${author} (${org || '[muassasa]'})
Mavzu: ${content}
To'liq rasmiy xat yozing.`;
  }
}

async function callGeminiDirectClient(prompt, imageFile) {
  const apiKey = (AppConfig.getGeminiApiKey ? AppConfig.getGeminiApiKey() : "") || atob("QVEuQWI4Uk42TFNiWGt4X2JMV1Z6S2tRbk5HTnBGaTN1OTBYY2FpWFhScV83S2xfaHlKc2c=");
  const parts = [];

  if (imageFile && imageFile.size) {
    const base64Data = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result.split(',')[1]);
      reader.readAsDataURL(imageFile);
    });
    parts.push({
      inlineData: {
        mimeType: imageFile.type || "image/jpeg",
        data: base64Data
      }
    });
  }

  parts.push({ text: prompt });

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key=${apiKey}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts }],
      generationConfig: {
        temperature: 0.3,
        maxOutputTokens: 2048
      }
    })
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    throw new Error(errData.error?.message || `Gemini API xatosi (${response.status})`);
  }

  const data = await response.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error("Gemini javob bermadi");
  return text.trim();
}

function createWordDownload(text, docType) {
  const htmlContent = `
    <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
    <head><meta charset='utf-8'><title>${docType}</title>
    <style>
      body { font-family: 'Times New Roman', serif; font-size: 12pt; line-height: 1.5; margin: 2.5cm; }
      p { margin: 0 0 6pt 0; text-align: justify; }
      .center { text-align: center; font-weight: bold; }
      .right { text-align: right; }
    </style>
    </head>
    <body>
      ${text.split('\n').map(line => {
        const trimmed = line.trim();
        if (!trimmed) return '<p>&nbsp;</p>';
        if (trimmed.toUpperCase() === trimmed && trimmed.length < 40) return `<p class="center">${trimmed}</p>`;
        return `<p>${trimmed}</p>`;
      }).join('')}
    </body>
    </html>
  `;
  const blob = new Blob(['\ufeff', htmlContent], { type: 'application/msword' });
  return URL.createObjectURL(blob);
}

document.getElementById('aiImageInput')?.addEventListener('change', function() {
  const nameEl = document.getElementById('aiImageName');
  if (this.files[0]) {
    nameEl.textContent = '📎 ' + this.files[0].name;
    nameEl.classList.remove('hidden');
  } else {
    nameEl.classList.add('hidden');
  }
});

document.getElementById('aiForm')?.addEventListener('submit', async function(e) {
  e.preventDefault();
  const btn = document.getElementById('aiWriteBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> AI yozmoqda...';

  const formData = new FormData(this);
  const docType = formData.get('doc_type') || 'ariza';
  const recipient = formData.get('recipient') || '';
  const authorName = formData.get('author_name') || '';
  const org = formData.get('organization') || '';
  const content = formData.get('content') || '';
  const imageFile = formData.get('image');

  if (!content && (!imageFile || !imageFile.size)) {
    Swal.fire({ icon: 'warning', title: 'Mazmun kerak', text: 'Hujjat mazmunini yozing yoki rasm yuklang.', confirmButtonColor: '#7c3aed' });
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> AI Hujjat Yozsin';
    return;
  }

  let generatedText = "";
  let wordCount = 0;
  let isClientGenerated = false;

  // 1-qadam: Avval Raspberry Pi serveriga urinib ko'rish
  const apiUrl = AppConfig.getApiUrl();
  let serverWorked = false;

  if (apiUrl) {
    try {
      const res = await fetch(`${apiUrl}/api/ai/write`, {
        method: 'POST',
        headers: { "ngrok-skip-browser-warning": "true" },
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          generatedText = data.text;
          wordCount = data.word_count;
          currentDocId = data.doc_id;
          serverWorked = true;
          document.getElementById('aiDownloadBtn').href = `${apiUrl}${data.download_url}`;
        }
      }
    } catch (e) {
      console.log("Server oflayn, to'g'ridan-to'g'ri brauzer orqali AI ishga tushirilmoqda...");
    }
  }

  // 2-qadam: Agar server oflayn bo'lsa — to'g'ridan-to'g'ri brauzer orqali Gemini chaqirish!
  if (!serverWorked) {
    try {
      const prompt = buildClientPrompt(docType, recipient, content, authorName, org);
      generatedText = await callGeminiDirectClient(prompt, imageFile);
      wordCount = generatedText.split(/\s+/).filter(Boolean).length;
      isClientGenerated = true;
      currentDocId = "client_" + Date.now();

      // Word yuklab olish havolasi yaratish
      const blobUrl = createWordDownload(generatedText, docType);
      const downloadBtn = document.getElementById('aiDownloadBtn');
      downloadBtn.href = blobUrl;
      downloadBtn.setAttribute('download', `${docType}_hujjati.doc`);
    } catch (err) {
      Swal.fire({
        icon: 'error',
        title: 'AI Xatosi',
        text: err.message || 'Gemini API bilan bog\'lanishda xatolik yuz berdi.',
        confirmButtonColor: '#7c3aed'
      });
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> AI Hujjat Yozsin';
      return;
    }
  }

  currentGeneratedText = generatedText;

  // Natijani ko'rsatish
  document.getElementById('aiResult').classList.remove('hidden');
  document.getElementById('aiTextPreview').textContent = generatedText;
  document.getElementById('aiWordCount').textContent = `${wordCount} so'z`;

  // Narx hisoblash
  const basePrice = DOC_TYPE_BASE_PRICES[docType] || 3000;
  const extraWords = Math.max(0, wordCount - 100);
  const extraPrice = Math.floor(extraWords / 100) * 500;
  const aiFee = basePrice + extraPrice;
  const printFee = 500;
  const totalFee = aiFee + printFee;

  const priceBox = document.getElementById('aiPriceBox');
  priceBox.classList.remove('hidden');
  document.getElementById('aiWriteFee').textContent = aiFee.toLocaleString() + " so'm";
  document.getElementById('aiPrintFee').textContent = printFee.toLocaleString() + " so'm";
  document.getElementById('aiTotalFee').textContent = totalFee.toLocaleString() + " so'm";

  document.getElementById('aiResult').scrollIntoView({ behavior: 'smooth' });

  btn.disabled = false;
  btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> AI Hujjat Yozsin';
});

document.getElementById('aiPrintBtn')?.addEventListener('click', async function() {
  if (!currentGeneratedText) return;
  const apiUrl = AppConfig.getApiUrl();

  if (!apiUrl) {
    Swal.fire({
      icon: 'info',
      title: 'Hujjat tayyor!',
      text: 'Hujjatni "Word yuklab ol" tugmasi orqali saqlab olishingiz mumkin. Chop etish uchun printer ulangan bo\'lishi kerak.',
      confirmButtonColor: '#2563eb'
    });
    return;
  }

  this.disabled = true;
  this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

  try {
    const totalFeeText = document.getElementById('aiTotalFee').textContent;
    const amount = totalFeeText.replace(/[^0-9]/g, '');
    const res = await fetch(`${apiUrl}/api/ai/print/${currentDocId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        "ngrok-skip-browser-warning": "true"
      },
      body: JSON.stringify({ color_mode: 'gray', copies: 1, amount })
    });
    const data = await res.json();
    Swal.fire({
      icon: data.success ? 'success' : 'error',
      title: data.success ? 'Chop etildi!' : 'Xatolik',
      text: data.message,
      confirmButtonColor: data.success ? '#2563eb' : '#e11d48'
    });
  } catch (e) {
    Swal.fire({
      icon: 'info',
      title: 'Hujjat tayyor!',
      text: 'Hujjat yaratildi! "Word yuklab ol" tugmasi orqali Word faylini yuklab oling.',
      confirmButtonColor: '#2563eb'
    });
  } finally {
    this.disabled = false;
    this.innerHTML = '<i class="fa-solid fa-print text-xs"></i> Chop Et';
  }
});

// ----------------- TO'LOV MODALI (PAYMENT MODAL) -----------------
const paymentModal = document.getElementById('paymentModal');
const paymentModalCard = document.getElementById('paymentModalCard');
const closePaymentModalBtn = document.getElementById('closePaymentModalBtn');
const cancelPaymentBtn = document.getElementById('cancelPaymentBtn');
const confirmPaymentBtn = document.getElementById('confirmPaymentBtn');

const modalCardNumber = document.getElementById('modalCardNumber');
const modalCardHolder = document.getElementById('modalCardHolder');
const cardBankTxt = document.getElementById('cardBankTxt');
const copyCardBtn = document.getElementById('copyCardBtn');
const copyCardTxt = document.getElementById('copyCardTxt');

const clickPayLink = document.getElementById('clickPayLink');
const paymePayLink = document.getElementById('paymePayLink');

let currentSelectedPayTab = 'card';

// To'lov tablarini almashtirish
document.querySelectorAll('.pay-tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tabName = btn.getAttribute('data-tab');
    currentSelectedPayTab = tabName;

    document.querySelectorAll('.pay-tab-btn').forEach(b => {
      b.classList.remove('bg-white', 'text-blue-700', 'shadow-sm', 'font-bold');
      b.classList.add('text-slate-600', 'font-medium');
    });
    btn.classList.add('bg-white', 'text-blue-700', 'shadow-sm', 'font-bold');
    btn.classList.remove('text-slate-600', 'font-medium');

    document.querySelectorAll('.pay-tab-content').forEach(c => c.classList.add('hidden'));
    const targetContent = document.getElementById(`tabContent${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`);
    if (targetContent) targetContent.classList.remove('hidden');
  });
});

// Nusxa olish
if (copyCardBtn) {
  copyCardBtn.addEventListener('click', () => {
    const num = modalCardNumber.textContent.replace(/\s+/g, '');
    navigator.clipboard.writeText(num).then(() => {
      copyCardTxt.textContent = 'Nusxalandi!';
      copyCardBtn.classList.add('bg-emerald-600');
      setTimeout(() => {
        copyCardTxt.textContent = 'Nusxa';
        copyCardBtn.classList.remove('bg-emerald-600');
      }, 2000);
    });
  });
}

function openPaymentModal() {
  const payCfg = AppConfig.getPaymentConfig();
  const totalPrice = parseInt(totalPriceTxt.textContent.replace(/\s+/g, '')) || 500;
  const copies = parseInt(copiesVal.value) || 1;

  document.getElementById('modalAmountTxt').textContent = totalPrice.toLocaleString();
  document.getElementById('modalOrderSummary').textContent = `${detectedPages} sahifa • ${copies} nusxa`;

  const cleanCard = (payCfg.cardNumber || '').replace(/\s+/g, '');
  if (cleanCard.length === 16) {
    modalCardNumber.textContent = cleanCard.replace(/(\d{4})/g, '$1 ').trim();
  } else {
    modalCardNumber.textContent = payCfg.cardNumber || 'Karta kiritilmagan';
  }

  modalCardHolder.textContent = payCfg.cardHolder || 'PRINT MARKAZ';
  cardBankTxt.textContent = payCfg.cardBank || 'UZCARD / HUMO';

  if (payCfg.clickMerchantId && payCfg.clickServiceId) {
    clickPayLink.href = `https://my.click.uz/services/pay?service_id=${payCfg.clickServiceId}&merchant_id=${payCfg.clickMerchantId}&amount=${totalPrice}`;
  } else if (payCfg.clickPhone) {
    const cleanPhone = payCfg.clickPhone.replace(/[^0-9]/g, '');
    clickPayLink.href = `https://my.click.uz/pay/transfer?phone=${cleanPhone}&amount=${totalPrice}`;
  } else if (cleanCard) {
    clickPayLink.href = `https://my.click.uz/pay/transfer?card=${cleanCard}&amount=${totalPrice}`;
  } else {
    clickPayLink.href = `https://my.click.uz`;
  }

  if (payCfg.paymeMerchantId) {
    const base64Order = btoa(`m=${payCfg.paymeMerchantId};a=${totalPrice * 100}`);
    paymePayLink.href = `https://checkout.paycom.uz/${base64Order}`;
  } else if (cleanCard) {
    paymePayLink.href = `https://payme.uz/fallback/pay/?card=${cleanCard}&amount=${totalPrice * 100}`;
  } else {
    paymePayLink.href = `https://payme.uz`;
  }

  paymentModal.classList.remove('opacity-0', 'pointer-events-none');
  paymentModalCard.classList.remove('scale-95');
  paymentModalCard.classList.add('scale-100');
}

function closePaymentModal() {
  paymentModal.classList.add('opacity-0', 'pointer-events-none');
  paymentModalCard.classList.remove('scale-100');
  paymentModalCard.classList.add('scale-95');
}

if (closePaymentModalBtn) closePaymentModalBtn.addEventListener('click', closePaymentModal);
if (cancelPaymentBtn) cancelPaymentBtn.addEventListener('click', closePaymentModal);

async function executePrintJob(paymentInfo) {
  const apiUrl = AppConfig.getApiUrl();
  closePaymentModal();

  Swal.fire({
    title: 'Chop etilmoqda...',
    html: `
      <div class="space-y-3 py-2 text-center">
        <div class="text-xs text-slate-500" id="swalStepText">To‘lov qabul qilindi. Fayl serverga yuklanmoqda...</div>
        <div class="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
          <div id="swalBar" class="bg-emerald-600 h-full rounded-full transition-all duration-500" style="width: 30%"></div>
        </div>
      </div>
    `,
    allowOutsideClick: false,
    allowEscapeKey: false,
    showConfirmButton: false,
    didOpen: () => { Swal.showLoading(); }
  });

  const formData = new FormData(printForm);
  if (paymentInfo) {
    formData.append('payment_method', paymentInfo.method || 'card');
    formData.append('amount', paymentInfo.amount || '0');
    formData.append('payment_status', 'PAID');
  }

  try {
    const res = await fetch(`${apiUrl}/api/print`, {
      method: 'POST',
      headers: { "ngrok-skip-browser-warning": "true" },
      body: formData
    });
    const result = await res.json();

    if (res.ok && result.success) {
      Swal.fire({
        icon: 'success',
        title: 'Chop Etish Boshlandi!',
        html: `
          <div class="text-sm text-slate-600 space-y-2">
            <p>${result.message}</p>
            <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-700 text-left space-y-1">
              <div><strong>Printer:</strong> ${result.printer}</div>
              <div><strong>Nusxalar:</strong> ${result.copies} ta</div>
            </div>
          </div>
        `,
        confirmButtonColor: '#16a34a'
      });
      printForm.reset();
      fileInfoBox.classList.add('hidden');
      promptContent.classList.remove('hidden');
      detectedPages = 1;
      updatePricing();
    } else {
      Swal.fire({ icon: 'error', title: 'Xatolik!', text: result.message, confirmButtonColor: '#e11d48' });
    }
  } catch (err) {
    Swal.fire({ icon: 'error', title: 'Aloqa uzildi!', text: 'Raspberry Pi bilan bog\'lanib bo\'lmadi.', confirmButtonColor: '#e11d48' });
  }
}

if (confirmPaymentBtn) {
  confirmPaymentBtn.addEventListener('click', () => {
    const totalPrice = parseInt(totalPriceTxt.textContent.replace(/\s+/g, '')) || 500;
    executePrintJob({
      method: currentSelectedPayTab,
      amount: totalPrice,
      status: 'PAID'
    });
  });
}

if (printForm) {
  printForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!fileInput.files.length) {
      Swal.fire({ icon: 'warning', title: 'Fayl tanlanmadi!', text: 'Chop etilishi kerak bo\'lgan faylni yuklang.', confirmButtonColor: '#2563eb' });
      return;
    }
    const apiUrl = AppConfig.getApiUrl();
    if (!apiUrl) {
      Swal.fire({ icon: 'error', title: 'Server ulanmagan!', text: 'Sozlamalar (⚙️) orqali API manzilini kiriting.', confirmButtonColor: '#2563eb' }).then(openSettingsModal);
      return;
    }
    openPaymentModal();
  });
}

// Dastlabki yuklash
updatePricing();
checkBackendHealth();
