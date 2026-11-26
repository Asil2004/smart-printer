/**
 * Smart Printchi — frontend ("Bento + Chat" UI)
 * ==============================================
 * Bitta ekran: chat yordamchi + bento kartochkalar + to'lov paneli.
 * Narx va sahifa soni har doim SERVERDA tasdiqlanadi (/api/order/create),
 * brauzerdagi hisob faqat oldindan ko'rsatish uchun.
 *
 * Backend API: /api/printers, /api/health, /api/inspect-file, /api/templates,
 *   /api/order/create, /api/order/<id>/claim, /api/order/status/<id>,
 *   /api/admin/templates/upload|delete (X-Admin-Token)
 */
(() => {
  'use strict';

  // ── Sozlamalar ──────────────────────────────────────────
  const MAX_BYTES = 64 * 1024 * 1024;
  const EXTS = ['pdf', 'docx', 'png', 'jpg', 'jpeg'];
  let MAX_COPIES = 50;   // /api/health dagi max_copies bilan yangilanadi
  const POLL_MS = 2000;
  const HDR = { 'ngrok-skip-browser-warning': 'true' };

  const $ = (id) => document.getElementById(id);
  const api = (path) => `${AppConfig.getApiUrl()}${path}`;

  // ── Holat ───────────────────────────────────────────────
  const S = {
    view: 'print',
    printerType: 'laser_bw', // 'laser_bw' (Canon A4) yoki 'thermal' (XP-58 Chek)
    file: null,            // File (shablon tanlansa: {name, size: 0})
    template: null,        // tanlangan shablon: hujjat kabi yuklanadi, nusxa tanlanadi
    fileExt: '',
    pages: 0,              // fayldagi jami betlar
    counting: false,
    copies: 1,
    orientation: 'portrait',
    color: 'gray',
    rangeMode: 'all',      // all | custom
    rangeText: '',
    priceBw: 250,
    priceColor: 400,
    printers: [],
    printerReady: false,
    colorReady: false,
    online: null,          // null = tekshirilmoqda
    userMsg: '',
    botLead: '',
    templates: [],
    order: null,           // {id, amount, pages, source}
    payMethod: 'qr',
    pollTimer: null,
    lastStatus: '',
  };

  // ── Yordamchi funksiyalar ───────────────────────────────
  const money = (n) => String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' so‘m';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtSize = (b) => b > 1048576 ? (b / 1048576).toFixed(1).replace('.', ',') + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';

  let toastTimer = null;
  function toast(text, kind = '') {
    const t = $('toast');
    t.textContent = text;
    t.className = 'toast' + (kind ? ' ' + kind : '');
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 4200);
  }

  function speak(text) {
    try {
      if (!('speechSynthesis' in window)) return;
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'uz-UZ';
      u.rate = 0.95;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    } catch (e) { /* ovoz ixtiyoriy */ }
  }

  async function getJSON(path, opts = {}) {
    const res = await fetch(api(path), { ...opts, headers: { ...HDR, ...(opts.headers || {}) } });
    let data = {};
    try { data = await res.json(); } catch (e) { /* bo'sh javob */ }
    return { ok: res.ok, status: res.status, data };
  }

  // Server bilan bir xil: "1-3, 5" → nechta bet
  function countSelected(text, total) {
    total = Math.max(1, total || 1);
    if (!text || /^(all|barchasi|hammasi)$/i.test(text.trim())) return total;
    let n = 0;
    for (let part of text.replace(/–/g, '-').split(',')) {
      part = part.trim();
      if (!part) continue;
      const m = part.match(/^(\d+)\s*-\s*(\d+)$/);
      if (m) {
        const a = Math.max(1, +m[1]), b = Math.min(total, +m[2]);
        if (b >= a) n += b - a + 1;
      } else if (/^\d+$/.test(part)) {
        const p = +part;
        if (p >= 1 && p <= total) n += 1;
      }
    }
    return n > 0 ? n : 0;
  }

  function normRange(text) {
    return text.replace(/–/g, '-').replace(/\s+/g, '').replace(/,+/g, ',').replace(/^,|,$/g, '');
  }

  function selectedPages() {
    if (!S.file) return 0;
    if (S.rangeMode === 'custom') return countSelected(S.rangeText, S.pages);
    return S.pages;
  }

  function unitPrice() {
    if (S.template) return S.template.price_per_page || S.priceBw;
    return S.color === 'color' ? S.priceColor : S.priceBw;
  }

  // ── Chat ────────────────────────────────────────────────
  function renderChat() {
    const box = $('chat');
    let html = '';
    if (!S.file) {
      html += `<div class="bubble bot"><span>Salom! Chop etmoqchi bo‘lgan faylni yuboring yoki tayyor shablonni tanlang.</span>${S.botLead ? `<strong>${esc(S.botLead)}</strong>` : ''}</div>`;
    } else {
      const ext = (S.fileExt || 'fayl').slice(0, 4);
      const sub = S.counting ? 'sahifalar sanalmoqda…' : (S.template ? `shablon, ${S.pages} bet` : `${S.pages} bet · ${fmtSize(S.file.size)}`);
      html += `<div class="file-bubble" data-kind="${S.template ? 'template' : 'file'}"><span class="file-badge">${esc(ext)}</span><span class="file-meta"><p class="file-name">${esc(S.file.name)}</p><p class="file-sub">${esc(sub)}</p></span></div>`;
      if (S.userMsg) html += `<p class="bubble user">${esc(S.userMsg)}</p>`;
      if (S.counting) {
        html += `<div class="bubble bot" aria-label="Yordamchi yozmoqda"><span class="typing"><span></span><span></span><span></span></span></div>`;
      } else {
        html += `<div class="bubble bot"><span>${esc(S.botLead || `${S.pages} bet topdim. Shunday chop etamizmi?`)}</span><strong>${esc(summaryLine())}</strong></div>`;
      }
    }
    box.innerHTML = html;
  }

  function summaryLine() {
    const sel = selectedPages();
    if (S.rangeMode === 'custom' && !sel) return 'Betlar oralig‘ini to‘g‘ri kiriting';
    const range = S.rangeMode === 'all' ? `barcha ${S.pages} bet` : `${normRange(S.rangeText).replace(/-/g, '-')} (${sel} bet)`;
    const orient = S.orientation === 'landscape' ? 'albom' : 'kitob';
    const color = S.color === 'color' ? 'rangli' : 'oq-qora';
    const prn = S.printerType === 'thermal' ? 'XP-58 chek' : 'Canon A4';
    return `${prn} · ${range} · ${orient} · ${color} · ${S.copies} nusxa = ${money(sel * S.copies * unitPrice())}`;
  }

  function renderChips() {
    const chips = $('chips');
    if (!S.file || S.counting) { chips.hidden = true; return; }
    const list = [];
    if (S.printerType === 'thermal') {
      list.push(['A4 printerga o‘tish', () => update({ printerType: 'laser_bw' }, 'Canon LBP3010 A4 lazer tanlandi.')]);
    } else {
      list.push(['Chek printerda chiqarish', () => update({ printerType: 'thermal' }, 'XP-58 termal chek printeri tanlandi.')]);
    }
    if (S.copies < 2) list.push(['2 nusxa', () => update({ copies: 2 }, 'Tushundim: 2 nusxa.')]);
    else list.push(['1 nusxa', () => update({ copies: 1 }, 'Tushundim: 1 nusxa.')]);
    if (S.pages > 3 && !(S.rangeMode === 'custom' && normRange(S.rangeText) === '1-3')) {
      list.push(['Faqat 1-3 bet', () => update({ rangeMode: 'custom', rangeText: '1-3' }, 'Tushundim: faqat 1-3 betlar.')]);
    }
    if (!S.template) list.push(S.orientation === 'portrait'
      ? ['Albom qilib', () => update({ orientation: 'landscape' }, 'Tushundim: albom yo‘nalishi.')]
      : ['Kitob qilib', () => update({ orientation: 'portrait' }, 'Tushundim: kitob yo‘nalishi.')]);
    list.push(['Boshqa fayl', () => $('fileInput').click()]);
    chips.innerHTML = '';
    for (const [label, fn] of list) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.textContent = label;
      b.addEventListener('click', fn);
      chips.appendChild(b);
    }
    chips.hidden = false;
  }

  // ── Kartochkalar va narx ────────────────────────────────
  function renderSettings() {
    const has = !!S.file;
    $('startGrid').hidden = has;
    $('settingsGrid').hidden = !has;
    const co = $('copiesOut');   // <input>: raqamni yozib ham kiritish mumkin
    if (document.activeElement !== co) co.value = S.copies;
    if ('max' in co) co.max = MAX_COPIES;
    $('copiesDec').disabled = S.copies <= 1;
    $('copiesInc').disabled = S.copies >= MAX_COPIES;
    document.querySelectorAll('[data-printer]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.printer === S.printerType)));
    document.querySelectorAll('[data-orient]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.orient === S.orientation)));
    document.querySelectorAll('[data-range]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.range === S.rangeMode)));
    document.querySelectorAll('[data-color]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.color === S.color)));
    const cb = $('colorBtn');
    cb.disabled = !S.colorReady;
    cb.title = S.colorReady ? `Rangli: ${money(S.priceColor)}/bet` : 'Rangli printer ulanmagan';
    ['lblOrient', 'lblPages', 'lblColor'].forEach((id) => { $(id).closest('.tile').hidden = !!S.template; });
    $('rangeTile').hidden = S.rangeMode !== 'custom' || !!S.template;
    if ($('rangeInput').value !== S.rangeText) $('rangeInput').value = S.rangeText;
    const sel = selectedPages();
    const hint = $('rangeHint');
    if (S.rangeMode === 'custom') {
      hint.className = 'hint' + (sel ? '' : ' err');
      hint.textContent = sel ? `${sel} bet tanlandi (jami ${S.pages})` : `1 dan ${S.pages} gacha bo‘lgan betlarni kiriting`;
    }
  }

  function renderPaybar() {
    const btn = $('payBtn');
    if (!S.file) {
      $('totalLabel').textContent = 'Fayl tanlanmagan';
      $('totalText').textContent = '0 so‘m';
      btn.disabled = true;
      return;
    }
    const sel = selectedPages();
    const prnLabel = S.printerType === 'thermal' ? 'XP-58 Chek' : 'Canon A4 Lazer';
    $('totalLabel').textContent = S.counting ? 'Hisoblanmoqda…' : `Jami · ${sel} bet × ${S.copies} nusxa [${prnLabel}]`;
    $('totalText').textContent = S.counting ? '…' : money(sel * S.copies * unitPrice());
    const canon = S.printers.find((p) => p.type === 'laser_bw' && p.connected);
    const thermal = S.printers.find((p) => p.type === 'thermal' && p.connected);
    const targetPrn = S.printerType === 'thermal' ? thermal : canon;
    const isReady = targetPrn ? targetPrn.ready : S.printerReady;
    btn.disabled = S.counting || !sel || !isReady;
    btn.title = isReady ? '' : (targetPrn ? (targetPrn.status_reason || 'Tanlangan printer band') : 'Printer hozir tayyor emas');
  }

  function renderStatus() {
    const el = $('printerStatus');
    const txt = $('printerStatusText');
    if (S.online === null) { el.className = 'status'; txt.textContent = 'Printer tekshirilmoqda…'; return; }
    if (!S.online) { el.className = 'status err'; txt.textContent = 'Server bilan aloqa yo‘q'; return; }

    const canon = S.printers.find((p) => p.type === 'laser_bw' && p.connected);
    const thermal = S.printers.find((p) => p.type === 'thermal' && p.connected);

    if (canon && thermal) {
      el.className = 'status ok';
      txt.textContent = 'Canon LBP3010 (Lazer) va XP-58 (Chek) tayyor';
    } else if (canon && canon.ready) {
      el.className = 'status ok';
      txt.textContent = `${canon.label || 'Canon LBP3010'} tayyor · navbat yo‘q`;
    } else if (thermal && thermal.ready) {
      el.className = 'status ok';
      txt.textContent = `${thermal.label || 'XP-58 Chek (Dev)'} tayyor`;
    } else if (canon) {
      el.className = 'status warn';
      txt.textContent = canon.status_reason || 'Canon band';
    } else if (thermal) {
      el.className = 'status warn';
      txt.textContent = thermal.status_reason || 'XP-58 band';
    } else {
      const any = S.printers.find((p) => p.connected);
      if (any) {
        el.className = any.ready ? 'status ok' : 'status warn';
        txt.textContent = any.label || 'Printer tayyor';
      } else {
        el.className = 'status err';
        txt.textContent = 'Printer ulanmagan';
      }
    }
  }

  function render() {
    $('viewPrint').hidden = S.view !== 'print';
    $('viewTemplates').hidden = S.view !== 'templates';
    $('navBtn').textContent = S.view === 'print' ? 'Shablonlar →' : '← Chop etish';
    renderStatus();
    renderChat();
    renderChips();
    renderSettings();
    renderPaybar();
  }

  function update(patch, lead) {
    Object.assign(S, patch);
    if (S.copies < 1) S.copies = 1;
    if (S.copies > MAX_COPIES) S.copies = MAX_COPIES;
    if (lead !== undefined) S.botLead = lead;
    render();
  }

  // ── Yozma buyruqlarni tushunish ─────────────────────────
  // "3 nusxa", "5-8 bet", "1,3,5", "albom", "kitob", "rangli", "oq-qora", "hammasi", "to'lash"
  function parseCommand(raw) {
    const t = raw.toLowerCase().replace(/[‘’ʻʼ`']/g, '\'').replace(/–|—/g, '-');
    const patch = {};
    const done = [];
    const cp = t.match(/(\d+)\s*(ta\s*)?(nusxa|dona|marta|x\b)/);
    if (cp) {
      patch.copies = Math.max(1, Math.min(MAX_COPIES, parseInt(cp[1], 10)));
      done.push(`${patch.copies} nusxa`);
    }
    const tNoCopies = cp ? t.replace(cp[0], ' ') : t;
    const rg = tNoCopies.match(/\d+\s*-\s*\d+(\s*,\s*\d+(\s*-\s*\d+)?)*|\d+(\s*,\s*\d+)+/);
    const single = tNoCopies.match(/(\d+)\s*-?\s*(bet|sahifa|varaq)/);
    if (rg) {
      patch.rangeMode = 'custom';
      patch.rangeText = normRange(rg[0]);
      done.push(`${patch.rangeText} betlar`);
    } else if (single) {
      patch.rangeMode = 'custom';
      patch.rangeText = single[1];
      done.push(`${single[1]}-bet`);
    } else if (/hammas|barcha|to'liq/.test(t)) {
      patch.rangeMode = 'all';
      patch.rangeText = '';
      done.push('barcha betlar');
    }
    if (/albom|yotiq|landscape/.test(t)) { patch.orientation = 'landscape'; done.push('albom'); }
    else if (/kitob|tik\b|portrait/.test(t)) { patch.orientation = 'portrait'; done.push('kitob'); }
    if (/oq-?qora|qora-?oq|\bbw\b/.test(t)) { patch.color = 'gray'; done.push('oq-qora'); }
    else if (/rangli/.test(t)) {
      if (S.colorReady) { patch.color = 'color'; done.push('rangli'); }
      else done.push('rangli printer hozir ulanmagan, oq-qora qoldi');
    }
    if (/xp-?58|chek|termal|receipt|pos|kvitansiya/.test(t)) {
      patch.printerType = 'thermal';
      done.push('XP-58 termal chek printeri');
    } else if (/canon|lazer|laser|a4|lbp/.test(t)) {
      patch.printerType = 'laser_bw';
      done.push('Canon LBP3010 A4 lazer printeri');
    }
    const wantsPay = /to'la|tola|chop et|bosib|tayyor|\bha\b/.test(t);
    return { patch, done, wantsPay };
  }

  async function triggerDevTest(target = 'thermal') {
    toast(`${target === 'thermal' ? 'XP-58 Chek' : 'Canon LBP'} test buyrug‘i yuborilmoqda...`);
    try {
      const { ok, data } = await getJSON('/api/dev/test_print', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target })
      });
      if (ok && data.success) {
        toast(`✅ #${data.order_id} ${target} sinov navbatga qo'yildi!`, 'ok');
      } else {
        toast('Test yuborilmadi', 'err');
      }
    } catch (e) {
      toast('Server bilan aloqa yo‘q', 'err');
    }
  }

  function onCommand(text) {
    text = text.trim();
    if (!text) return;

    // Dasturchi buyruqlari
    const lower = text.toLowerCase();
    if (lower === 'test' || lower === 'sinov' || lower === 'xp58' || lower === 'chek' || lower === 'dev') {
      triggerDevTest('thermal');
      return;
    }
    if (lower === 'canon' || lower === 'lazer') {
      triggerDevTest('laser_bw');
      return;
    }

    if (!S.file) {
      update({ userMsg: '' }, 'Avval faylni yuboring: pastdagi qisqich tugmasi yoki «Faylni tanlang».');
      toast('Avval faylni tanlang');
      return;
    }
    const { patch, done, wantsPay } = parseCommand(text);
    S.userMsg = text;
    if (done.length) {
      update(patch, `Tushundim: ${done.join(', ')}. Yangi hisob:`);
    } else if (wantsPay) {
      update({}, 'Yaxshi, to‘lov oynasini ochyapman.');
    } else {
      update({}, 'Kechirasiz, tushunmadim. «2 nusxa», «5-8 bet», «albom» yoki «to‘lash» deb yozing.');
    }
    if (wantsPay && !$('payBtn').disabled) payNow();
  }

  // PDF sahifalarini brauzerda 0.01 soniyada (serverga yuklamasdan) tezkor sanash
  async function countPdfPagesFast(file) {
    try {
      const size = file.size;
      const tailBytes = Math.min(size, 131072); // 128 KB
      // 1. Oxiridan 128KB tekshirish
      const tailBlob = file.slice(size - tailBytes, size);
      const tailText = await tailBlob.text();
      let maxCount = 0;
      const matches = [...tailText.matchAll(/\/Count\s+(\d+)/g)];
      for (const m of matches) {
        const val = parseInt(m[1], 10);
        if (!isNaN(val) && val > maxCount && val < 5000) maxCount = val;
      }
      if (maxCount > 0) return maxCount;

      // 2. Boshidan 128KB tekshirish
      const headBlob = file.slice(0, tailBytes);
      const headText = await headBlob.text();
      const headMatches = [...headText.matchAll(/\/Count\s+(\d+)/g)];
      for (const m of headMatches) {
        const val = parseInt(m[1], 10);
        if (!isNaN(val) && val > maxCount && val < 5000) maxCount = val;
      }
      if (maxCount > 0) return maxCount;
    } catch (e) {
      console.warn('Fast PDF count error:', e);
    }
    return 0;
  }

  // ── Fayl ────────────────────────────────────────────────
  async function onFile(file) {
    if (!file) return;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!EXTS.includes(ext)) { toast('Bu format qabul qilinmaydi. PDF, DOCX, JPG yoki PNG yuboring.', 'err'); return; }
    if (file.size > MAX_BYTES) { toast('Fayl 64 MB dan katta.', 'err'); return; }
    S.view = 'print';
    S.template = null;

    // Rasm bo'lsa darhol 1 bet (serverga so'rovsiz chaqmoqdek ochiladi)
    if (['png', 'jpg', 'jpeg'].includes(ext)) {
      update({ file, fileExt: ext, pages: 1, counting: false, copies: 1, rangeMode: 'all', rangeText: '', userMsg: '', color: 'gray' }, '');
      speak('Rasm qabul qilindi.');
      return;
    }

    // PDF bo'lsa brauzerda 0.01 soniyada tezkor sahifalar sonini aniqlash (katta fayllar ham qotmaydi)
    if (ext === 'pdf') {
      const fastCount = await countPdfPagesFast(file);
      if (fastCount > 0) {
        update({ file, fileExt: ext, pages: fastCount, counting: false, copies: 1, rangeMode: 'all', rangeText: '', userMsg: '', color: 'gray', printerType: 'laser_bw' }, '');
        speak(`${fastCount} bet topildi.`);
        return;
      }
    }

    // DOCX yoki aniqlab bo'lmagan PDF uchun server orqali tekshirish
    update({ file, fileExt: ext, pages: 1, counting: true, copies: 1, rangeMode: 'all', rangeText: '', userMsg: '', color: 'gray', printerType: 'laser_bw' }, '');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { ok, data } = await getJSON('/api/inspect-file', { method: 'POST', body: fd });
      if (!ok || !data.success) throw new Error(data.error || 'Faylni o‘qib bo‘lmadi');
      update({ pages: Math.max(1, data.page_count || 1), counting: false }, '');
      speak(`${S.pages} bet topildi.`);
    } catch (e) {
      update({ pages: 1, counting: false }, 'Sahifalarni sanab bo‘lmadi. Narx to‘lov oynasida aniq hisoblanadi.');
      if (!S.online) toast('Server bilan aloqa yo‘q. Internetni tekshiring.', 'err');
    }
  }

  // ── Printer holati ──────────────────────────────────────
  async function refreshPrinters() {
    try {
      const { ok, data } = await getJSON('/api/printers');
      if (!ok) throw new Error();
      S.online = true;
      S.printers = data.printers || [];
      S.autoPay = !!data.auto_payment;
      const bw = S.printers.find((p) => p.type === 'laser_bw');
      const any = bw || S.printers.find((p) => p.connected && p.ready);
      S.printerReady = !!(any && any.connected && any.ready);
      const col = S.printers.find((p) => p.type === 'color');
      S.colorReady = !!(col && col.connected && col.ready);
      if (!S.colorReady && S.color === 'color') S.color = 'gray';
    } catch (e) {
      S.online = false;
      S.printerReady = false;
    }
    renderStatus();
    renderSettings();
    renderPaybar();
  }

  async function loadHealth() {
    try {
      const { ok, data } = await getJSON('/api/health');
      if (ok) {
        S.priceBw = data.price_bw || S.priceBw;
        S.priceColor = data.price_color || S.priceColor;
        if (data.max_copies) { MAX_COPIES = data.max_copies; renderSettings(); }
      }
    } catch (e) { /* ixtiyoriy */ }
  }

  // ── Shablonlar ──────────────────────────────────────────
  async function loadTemplates() {
    try {
      const { ok, data } = await getJSON('/api/templates');
      S.templates = ok ? (data.templates || []).filter((t) => t.file_exists !== false) : [];
    } catch (e) { S.templates = []; }
    renderTemplates();
    renderQuickTemplates();
    if (!$('adminOverlay').hidden) renderAdminList();
  }

  const docIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>';

  function tplPrice(t) { return (t.price_per_page || S.priceBw) * (t.pages || 1); }

  function renderTemplates() {
    const grid = $('tplGrid');
    const q = ($('tplSearch').value || '').toLowerCase().trim();
    const list = S.templates.filter((t) => !q || [t.name, t.description, ...(t.tags || [])].join(' ').toLowerCase().includes(q));
    if (!list.length) {
      grid.innerHTML = `<p class="empty">${S.templates.length ? 'Hech narsa topilmadi.' : 'Shablonlar yuklanmadi. Server bilan aloqani tekshiring.'}</p>`;
      return;
    }
    grid.innerHTML = list.map((t) => `
      <button class="tpl" type="button" data-tpl="${esc(t.id)}">
        ${previewSrc(t) ? `<span class="tpl-thumb"><img src="${esc(previewSrc(t))}" alt="" loading="lazy"></span>` : `<span class="ico" style="color:#1B1F23">${docIcon}</span>`}
        <b>${esc(t.name)}</b>
        <span class="desc">${esc(t.description || '')}</span>
        <span class="price">${t.pages || 1} bet · ${money(tplPrice(t))}</span>
      </button>`).join('');
  }

  function renderQuickTemplates() {
    const box = $('quickTemplates');
    box.innerHTML = S.templates.slice(0, 2).map((t) => `
      <button class="tpl-mini" type="button" data-tpl="${esc(t.id)}">
        <span class="ico" style="color:#C6F36B">${docIcon}</span>
        <b>${esc(t.name)}</b>
        <span>${money(tplPrice(t))}</span>
      </button>`).join('');
  }

  function onTemplateClick(e) {
    const btn = e.target.closest('[data-tpl]');
    if (!btn) return;
    const t = S.templates.find((x) => x.id === btn.dataset.tpl);
    if (!t) return;
    if (!S.printerReady) { toast('Printer hozir tayyor emas. Birozdan so‘ng urinib ko‘ring.', 'err'); return; }
    S.view = 'print';
    update({ template: t, file: { name: t.name, size: 0 }, fileExt: (t.file || 'docx').split('.').pop(), pages: t.pages || 1,
      counting: false, copies: 1, rangeMode: 'all', rangeText: '', userMsg: '', color: 'gray', orientation: 'portrait' },
      `“${t.name}” tanlandi. Nusxa sonini tanlang, keyin to‘lang.`);
  }

  const payNow = () => openPay(S.template ? { kind: 'template', template: S.template } : { kind: 'file' });

  // ── To'lov ──────────────────────────────────────────────
  function payTargets(amount, orderId) {
    const cfg = AppConfig.getPaymentConfig();
    const card = (cfg.cardNumber || '').replace(/\s+/g, '');
    const cardPretty = card.replace(/(\d{4})(?=\d)/g, '$1 ');
    const clickMerchant = cfg.clickMerchantId && cfg.clickServiceId;
    const clickUrl = clickMerchant
      ? `https://my.click.uz/services/pay?service_id=${cfg.clickServiceId}&merchant_id=${cfg.clickMerchantId}&amount=${amount}&transaction_param=${orderId}`
      : (card ? `https://my.click.uz/pay/transfer?card=${card}&amount=${amount}` : 'https://my.click.uz');
    const paymeUrl = cfg.paymeMerchantId
      ? `https://checkout.paycom.uz/${btoa(`m=${cfg.paymeMerchantId};a=${amount * 100};ac.order_id=${orderId}`)}`
      : (card ? `https://payme.uz/fallback/pay/?card=${card}&amount=${amount * 100}` : 'https://payme.uz');
    const qrData = clickMerchant ? clickUrl : (card || clickUrl);
    return { card, cardPretty, holder: cfg.cardHolder || '', bank: cfg.cardBank || '', clickUrl, paymeUrl, qrData };
  }

  function renderPayPanel() {
    const panel = $('payPanel');
    const o = S.order;
    document.querySelectorAll('[data-method]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.method === S.payMethod)));
    if (!o) { panel.innerHTML = '<span class="typing" aria-label="Kutilmoqda"><span></span><span></span><span></span></span>'; return; }
    const p = payTargets(o.amount, o.id);
    const cardBlock = `<p class="card-no">${esc(p.cardPretty || 'Karta kiritilmagan')}</p><p class="holder">${esc(p.holder)}${p.bank ? ' · ' + esc(p.bank) : ''}</p>`;
    if (S.payMethod === 'qr') {
      panel.innerHTML = `<img alt="To‘lov QR-kodi: ${esc(money(o.amount))}" src="https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=8&data=${encodeURIComponent(p.qrData)}">
        <p class="hint">Click yoki Payme ilovasida QR-kodni skanerlang va <b>${esc(money(o.amount))}</b> o‘tkazing.</p>`;
    } else if (S.payMethod === 'click') {
      panel.innerHTML = `${cardBlock}<a class="pay-link" href="${esc(p.clickUrl)}" target="_blank" rel="noopener">Click’da ${esc(money(o.amount))} to‘lash</a>`;
    } else if (S.payMethod === 'payme') {
      panel.innerHTML = `${cardBlock}<a class="pay-link" href="${esc(p.paymeUrl)}" target="_blank" rel="noopener">Payme’da ${esc(money(o.amount))} to‘lash</a>`;
    } else {
      panel.innerHTML = `${cardBlock}<button class="btn-ghost" type="button" id="copyCard">Karta raqamini nusxalash</button>
        <p class="hint">Istalgan bank ilovasidan aynan <b>${esc(money(o.amount))}</b> o‘tkazing.</p>`;
      const cc = $('copyCard');
      if (cc) cc.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(p.card); toast('Karta raqami nusxalandi'); }
        catch (e) { toast(p.cardPretty); }
      });
    }
  }

  function setPayStatus(kind, text) {
    const el = $('payStatus');
    el.className = 'pay-status' + (kind ? ' ' + kind : '');
    el.textContent = text;
  }

  async function openPay(src) {
    if (S.order) return;
    S.payMethod = 'qr';
    S.lastStatus = '';
    $('payOverlay').hidden = false;
    $('orderCode').textContent = '#······';
    $('payAmount').textContent = '... so‘m';
    $('paySummary').textContent = 'Buyurtma tayyorlanmoqda…';
    $('payClaim').disabled = true;
    resetPromo();
    if (src.kind !== 'template' && S.file && S.file.size > 2 * 1024 * 1024) {
      setPayStatus('', `Fayl serverga yuklanmoqda (${(S.file.size / (1024 * 1024)).toFixed(1)} MB)…`);
    } else {
      setPayStatus('', 'Buyurtma yaratilmoqda…');
    }
    renderPayPanel();
    $('payCancel').focus();

    const fd = new FormData();
    fd.append('printer_type', S.printerType || 'laser_bw');
    if (src.kind === 'template') {
      fd.append('source', 'template');
      fd.append('template_id', src.template.id);
      fd.append('copies', String(S.copies));
    } else {
      fd.append('source', 'file');
      fd.append('file', S.file);
      fd.append('copies', String(S.copies));
      fd.append('color_mode', S.color);
      fd.append('orientation', S.orientation);
      fd.append('page_ranges', S.rangeMode === 'custom' ? normRange(S.rangeText) : '');
    }
    try {
      const { status, data } = await getJSON('/api/order/create', { method: 'POST', body: fd });
      if (!data.success) {
        throw new Error(data.message || (status === 503 ? 'Printer hozir band.' : 'Buyurtma yaratilmadi.'));
      }
      S.order = { id: data.order_id, amount: data.amount, pages: data.pages, src };
      $('orderCode').textContent = '#' + data.order_id;
      $('payAmount').textContent = money(data.amount);
      const pageCount = (data && data.pages) || S.pages || 1;
      $('paySummary').textContent = src.kind === 'template'
        ? `Shablon: ${src.template.name}`
        : `${pageCount} bet × ${S.copies} nusxa · ${S.color === 'color' ? 'rangli' : 'oq-qora'}`;
      $('payClaim').disabled = false;
      $('promoBtn').disabled = false;
      setPayStatus('', S.autoPay
        ? `Aynan ${money(data.amount)} o‘tkazing — pul tushishi bilan avtomatik chop etiladi`
        : 'To‘lov kutilmoqda');
      renderPayPanel();
      startPolling();
    } catch (e) {
      closePay();
      toast(e.message || 'Server bilan aloqa yo‘q.', 'err');
    }
  }

  // ── Promokod ──
  function resetPromo() {
    const f = $('promoForm');
    f.classList.remove('applied');
    $('promoInput').value = '';
    $('promoInput').disabled = false;
    $('promoBtn').disabled = true;
    $('promoBtn').textContent = 'Qo‘llash';
  }

  async function applyPromo(e) {
    e.preventDefault();
    if (!S.order) return;
    const code = $('promoInput').value.trim();
    if (!code) { $('promoInput').focus(); return; }
    $('promoBtn').disabled = true;
    try {
      const { data } = await getJSON(`/api/order/${S.order.id}/promo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      if (!data || !data.success) {
        $('promoBtn').disabled = false;
        setPayStatus('err', (data && data.message) || 'Promokod qabul qilinmadi');
        return;
      }
      S.order.amount = data.amount;
      $('promoForm').classList.add('applied');
      $('promoInput').disabled = true;
      $('promoBtn').textContent = `−${data.percent}%`;
      const amt = $('payAmount');
      amt.textContent = '';
      const was = document.createElement('span');
      was.className = 'amount-was';
      was.textContent = money(data.amount_before);
      amt.append(was, document.createTextNode(money(data.amount)));
      if (data.free) {
        $('payClaim').disabled = true;
        $('payPanel').textContent = '';
        setPayStatus('ok', 'Promokod qabul qilindi — to‘lov shart emas, chop etilmoqda…');
        speak('Promokod qabul qilindi. Hujjatingiz chop etilmoqda.');
      } else {
        setPayStatus('', `Promokod qabul qilindi: ${money(data.amount)} to‘lang`);
        renderPayPanel();
      }
    } catch (err) {
      $('promoBtn').disabled = false;
      toast('Aloqa uzildi. Qayta urinib ko‘ring.', 'err');
    }
  }

  function closePay() {
    stopPolling();
    S.order = null;
    $('payOverlay').hidden = true;
  }

  async function cancelPay() {
    // Buyurtma serverda o'z-o'zidan eskiradi (30 daqiqa) — bu yerda faqat oynani yopamiz
    closePay();
  }

  async function claimPay() {
    if (!S.order) return;
    $('payClaim').disabled = true;
    try {
      const { status, data } = await getJSON(`/api/order/${S.order.id}/claim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method: S.payMethod }),
      });
      if (status === 404 || (data && data.status === 'NOT_FOUND')) {
        $('payClaim').disabled = false;
        setPayStatus('err', 'Buyurtma eskirgan. Bekor qilib qayta yuboring.');
        return;
      }
      setPayStatus('info', 'To‘lov tekshirilmoqda… biroz kuting');
      speak('Rahmat. To‘lov tekshirilmoqda, biroz kuting.');
    } catch (e) {
      $('payClaim').disabled = false;
      toast('Aloqa uzildi. Qayta urinib ko‘ring.', 'err');
    }
  }

  function startPolling() {
    stopPolling();
    S.pollTimer = setInterval(pollOnce, POLL_MS);
  }
  function stopPolling() {
    if (S.pollTimer) clearInterval(S.pollTimer);
    S.pollTimer = null;
  }

  async function pollOnce() {
    if (!S.order) return stopPolling();
    let data;
    try { ({ data } = await getJSON(`/api/order/status/${S.order.id}`)); } catch (e) { return; }
    if (!data || !data.success) return;
    const st = data.status;
    if (st === S.lastStatus && st !== 'PRINTING') return;
    S.lastStatus = st;
    switch (st) {
      case 'PENDING':
        if (!$('promoForm').classList.contains('applied')) {
          setPayStatus('', S.autoPay
            ? `Aynan ${money(S.order.amount)} o‘tkazing — pul tushishi bilan avtomatik chop etiladi`
            : 'To‘lov kutilmoqda');
        }
        break;
      case 'CLAIMED': setPayStatus('info', 'To‘lov tekshirilmoqda… biroz kuting'); $('payClaim').disabled = true; break;
      case 'PAID':
      case 'PRINTING':
        $('payClaim').disabled = true;
        setPayStatus(data.note ? '' : 'ok', data.note ? data.note : 'To‘lov tasdiqlandi, chop etilmoqda…');
        break;
      case 'PRINTED': {
        const id = S.order.id;
        const wasFile = S.order.src.kind === 'file';
        closePay();
        showResult(true, 'Hujjat tayyor!', `Buyurtma #${id} chop etildi. Qog‘ozni printer patnisidan oling.`);
        speak('To‘lov qabul qilindi. Hujjatingiz tayyor. Qog‘ozingizni oling!');
        if (wasFile) resetFile();
        break;
      }
      case 'FAILED': {
        const id = S.order.id;
        const errReason = data.error ? ` (${data.error})` : '';
        closePay();
        showResult(false, 'Printer xatosi', `To‘lovingiz qabul qilingan, lekin printer chop eta olmadi: ${errReason || 'qog‘oz yoki ulanishni tekshiring'}. Buyurtma: #${id}`);
        break;
      }
      case 'REJECTED':
      case 'CANCELLED':
      case 'EXPIRED': {
        const id = S.order.id;
        closePay();
        showResult(false, st === 'EXPIRED' ? 'Vaqt tugadi' : 'To‘lov tasdiqlanmadi',
          `Buyurtma #${id} uchun to‘lov topilmadi. Agar pul yechilgan bo‘lsa, bu kodni adminga ko‘rsating.`);
        break;
      }
    }
  }

  const iconOk = '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#1B1F23" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg>';
  const iconErr = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#B91C1C" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8v5M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg>';

  function showResult(ok, title, text) {
    $('resultIcon').className = 'result-icon' + (ok ? '' : ' err');
    $('resultIcon').innerHTML = ok ? iconOk : iconErr;
    $('resultTitle').textContent = title;
    $('resultText').textContent = text;
    $('resultBtn').textContent = ok ? 'Yangi buyurtma' : 'Tushunarli';
    $('resultOverlay').hidden = false;
    $('resultBtn').focus();
  }

  function resetFile() {
    $('fileInput').value = '';
    update({ file: null, template: null, fileExt: '', pages: 0, copies: 1, rangeMode: 'all', rangeText: '', userMsg: '', color: 'gray' }, '');
  }

  // ── Admin (logo bosilganda) ─────────────────────────────
  const adminToken = () => { try { return localStorage.getItem('PRINTCHI_ADMIN_TOKEN') || ''; } catch (e) { return ''; } };
  const setAdminToken = (v) => { try { if (v) localStorage.setItem('PRINTCHI_ADMIN_TOKEN', v); else localStorage.removeItem('PRINTCHI_ADMIN_TOKEN'); } catch (e) { /* */ } };
  const adminHdr = () => ({ 'X-Admin-Token': adminToken() });
  const previewSrc = (t) => (t.preview ? api(t.preview) : '');
  let adminTab = 'templates';

  function openAdmin() {
    $('adminOverlay').hidden = false;
    $('adminToken').value = '';
    try { $('adminLogin').value = localStorage.getItem('PRINTCHI_ADMIN_LOGIN') || ''; } catch (e) { /* */ }
    const t = adminToken();
    // Sessiya muddati o'tgan bo'lsa — so'rov yubormasdan kirish oynasi
    const exp = /^s1\.(\d+)\./.exec(t);
    if (t && (!exp || +exp[1] * 1000 > Date.now())) unlockAdmin(); else { setAdminToken(''); showAdminLock(); }
  }

  function showAdminLock() {
    $('adminTokenForm').hidden = false;
    $('adminBody').hidden = true;
    $('adminLogout').hidden = true;
    setTimeout(() => ($('adminLogin').value ? $('adminToken') : $('adminLogin')).focus(), 60);
  }

  async function unlockAdmin(fromForm = false) {
    const { status, data } = await getJSON('/api/admin/promos', { headers: adminHdr() }).catch(() => ({ status: 0, data: {} }));
    if (status === 401) { setAdminToken(''); showAdminLock(); toast('Sessiya tugagan. Qaytadan kiring.', 'err'); return; }
    if (!data.success) { showAdminLock(); toast('Server bilan aloqa yo‘q. Birozdan so‘ng urinib ko‘ring.', 'err'); return; }
    $('adminTokenForm').hidden = true;
    $('adminBody').hidden = false;
    $('adminLogout').hidden = false;
    S.promos = data.promos || [];
    renderAdminList();
    renderPromos();
    setAdminTab(adminTab);
    if (fromForm) toast('Admin panelga kirdingiz');
  }

  function setAdminTab(tab) {
    adminTab = tab;
    document.querySelectorAll('[data-admin-tab]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.adminTab === tab)));
    $('adminTemplates').hidden = tab !== 'templates';
    $('adminPromos').hidden = tab !== 'promos';
  }

  function renderAdminList() {
    if ($('adminBody').hidden) return;
    $('adminList').innerHTML = S.templates.map((t) => `
      <figure class="admin-tpl">
        <span class="thumb">${previewSrc(t) ? `<img src="${esc(previewSrc(t))}" alt="" loading="lazy">` : docIcon}</span>
        <figcaption><b>${esc(t.name)}</b><span>${t.pages || 1} bet · ${money(tplPrice(t))}</span></figcaption>
        <button type="button" data-del="${esc(t.id)}" aria-label="${esc(t.name)} shablonini o‘chirish">O‘chirish</button>
      </figure>`).join('') || '<p class="empty">Hali shablon yo‘q</p>';
  }

  async function adminUpload(e) {
    e.preventDefault();
    const btn = $('adminUploadBtn');
    const fd = new FormData(e.target);
    fd.append('category', 'other');
    btn.disabled = true;
    btn.textContent = 'Yuklanmoqda… rasm tayyorlanmoqda';
    try {
      const { status, data } = await getJSON('/api/admin/templates/upload', { method: 'POST', body: fd, headers: adminHdr() }).catch(() => ({ data: {} }));
      if (status === 401) { setAdminToken(''); showAdminLock(); toast('Sessiya tugagan. Qaytadan kiring.', 'err'); return; }
      if (!data.success) { toast(data.message || 'Yuklab bo‘lmadi', 'err'); return; }
      toast(`“${data.template.name}” qo‘shildi (${data.template.pages} bet)`);
      e.target.reset();
      await loadTemplates();
    } finally {
      btn.disabled = false;
      btn.textContent = 'Shablonni yuklash';
    }
  }

  async function adminDelete(id) {
    const t = S.templates.find((x) => x.id === id);
    if (!t || !window.confirm(`«${t.name}» shablonini o‘chirasizmi?`)) return;
    const { status, data } = await getJSON(`/api/admin/templates/delete/${encodeURIComponent(id)}`, { method: 'DELETE', headers: adminHdr() }).catch(() => ({ data: {} }));
    if (status === 401) { setAdminToken(''); showAdminLock(); toast('Sessiya tugagan. Qaytadan kiring.', 'err'); return; }
    if (!data.success) { toast(data.message || 'O‘chirib bo‘lmadi', 'err'); return; }
    toast('O‘chirildi');
    await loadTemplates();
  }

  function promoLine(p) {
    const bits = [`−${p.percent}%`, `${p.used}/${p.max_uses || '∞'} ishlatildi`];
    if (p.expires_at) bits.push(p.expired ? 'muddati tugagan' : `${new Date(p.expires_at * 1000).toLocaleDateString('uz-UZ')} gacha`);
    if (p.note) bits.push(p.note);
    return bits.join(' · ');
  }

  function renderPromos() {
    const list = S.promos || [];
    $('promoList').innerHTML = list.map((p) => {
      const off = p.expired || (p.max_uses && p.used >= p.max_uses);
      return `
      <div class="admin-item promo-item${off ? ' off' : ''}">
        <div><b class="mono">${esc(p.code)}</b><span>${esc(promoLine(p))}</span></div>
        <button type="button" class="btn-copy" data-copy="${esc(p.code)}">Nusxa</button>
        ${p.source === 'env'
          ? '<span class="promo-env" title="Render → Environment → PROMO_CODES">server</span>'
          : `<button type="button" data-pdel="${esc(p.code)}" aria-label="${esc(p.code)} promokodini o‘chirish">O‘chirish</button>`}
      </div>`;
    }).join('') || '<p class="empty">Hali promokod yo‘q</p>';
  }

  async function reloadPromos() {
    const { data } = await getJSON('/api/admin/promos', { headers: adminHdr() }).catch(() => ({ data: {} }));
    if (data.success) { S.promos = data.promos || []; renderPromos(); }
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { return false; }
  }

  async function createPromo(e) {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = { code: f.get('code'), percent: +f.get('percent'), max_uses: +f.get('max_uses') || 0, days: +f.get('days') || 0, note: f.get('note') };
    const { status, data } = await getJSON('/api/admin/promos', {
      method: 'POST', body: JSON.stringify(body), headers: { ...adminHdr(), 'Content-Type': 'application/json' },
    }).catch(() => ({ data: {} }));
    if (status === 401) { setAdminToken(''); showAdminLock(); toast('Sessiya tugagan. Qaytadan kiring.', 'err'); return; }
    if (!data.success) { toast(data.message || 'Yaratib bo‘lmadi', 'err'); return; }
    const copied = await copyText(data.promo.code);
    toast(`Promokod ${data.promo.code} yaratildi${copied ? ' va nusxalandi' : ''}`);
    e.target.reset();
    await reloadPromos();
  }

  async function deletePromo(code) {
    if (!window.confirm(`${code} promokodini o‘chirasizmi?`)) return;
    const { data } = await getJSON(`/api/admin/promos/${encodeURIComponent(code)}`, { method: 'DELETE', headers: adminHdr() }).catch(() => ({ data: {} }));
    if (!data.success) { toast(data.message || 'O‘chirib bo‘lmadi', 'err'); return; }
    toast('Promokod o‘chirildi');
    await reloadPromos();
  }

  // ── Hodisalar ───────────────────────────────────────────
  function bind() {
    $('navBtn').addEventListener('click', () => {
      S.view = S.view === 'print' ? 'templates' : 'print';
      render();
      if (S.view === 'templates') $('tplSearch').focus();
    });
    $('brandBtn').addEventListener('click', openAdmin);        // logo — admin panel

    $('dropZone').addEventListener('click', () => $('fileInput').click());
    $('attachBtn').addEventListener('click', () => $('fileInput').click());
    $('fileInput').addEventListener('change', (e) => onFile(e.target.files[0]));
    const dz = $('dropZone');
    ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('over'); }));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('over'); }));
    dz.addEventListener('drop', (e) => onFile(e.dataTransfer.files[0]));
    document.addEventListener('dragover', (e) => e.preventDefault());
    document.addEventListener('drop', (e) => { e.preventDefault(); if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]); });

    $('copiesDec').addEventListener('click', () => update({ copies: S.copies - 1 }, 'Yangiladim, chekka qarang.'));
    $('copiesInc').addEventListener('click', () => update({ copies: S.copies + 1 }, 'Yangiladim, chekka qarang.'));
    $('copiesOut').addEventListener('change', (e) => {
      const n = parseInt(e.target.value, 10);
      const lead = n > MAX_COPIES ? `Bir buyurtmada eng ko‘pi ${MAX_COPIES} nusxa.` : 'Yangiladim, chekka qarang.';
      update({ copies: Number.isFinite(n) ? n : 1 }, lead);
      e.target.value = S.copies;
    });
    $('copiesOut').addEventListener('keydown', (e) => { if (e.key === 'Enter') e.target.blur(); });
    document.querySelectorAll('[data-printer]').forEach((b) => b.addEventListener('click', () => {
      const pt = b.dataset.printer;
      const msg = pt === 'thermal'
        ? 'XP-58 termal chek printeri tanlandi (tezkor chek / dasturchi rejimi).'
        : 'Canon LBP3010 (A4 lazer) printeri tanlandi.';
      update({ printerType: pt }, msg);
    }));
    document.querySelectorAll('[data-orient]').forEach((b) => b.addEventListener('click', () => update({ orientation: b.dataset.orient }, 'Yangiladim, chekka qarang.')));
    document.querySelectorAll('[data-color]').forEach((b) => b.addEventListener('click', () => update({ color: b.dataset.color }, 'Yangiladim, chekka qarang.')));
    document.querySelectorAll('[data-range]').forEach((b) => b.addEventListener('click', () => {
      update({ rangeMode: b.dataset.range }, 'Yangiladim, chekka qarang.');
      if (b.dataset.range === 'custom') $('rangeInput').focus();
    }));
    $('rangeInput').addEventListener('input', (e) => { S.rangeText = e.target.value; S.botLead = 'Yangiladim, chekka qarang.'; renderChat(); renderSettings(); renderPaybar(); });

    $('composer').addEventListener('submit', (e) => {
      e.preventDefault();
      const v = $('msgInput').value;
      $('msgInput').value = '';
      onCommand(v);
    });

    $('payBtn').addEventListener('click', payNow);
    $('tplGrid').addEventListener('click', onTemplateClick);
    $('quickTemplates').addEventListener('click', onTemplateClick);
    $('tplSearch').addEventListener('input', renderTemplates);

    document.querySelectorAll('[data-method]').forEach((b) => b.addEventListener('click', () => { S.payMethod = b.dataset.method; renderPayPanel(); }));
    $('payClaim').addEventListener('click', claimPay);
    $('promoForm').addEventListener('submit', applyPromo);
    $('promoInput').addEventListener('input', () => { if (S.order && !$('promoForm').classList.contains('applied')) $('promoBtn').disabled = !$('promoInput').value.trim(); });
    $('payCancel').addEventListener('click', cancelPay);
    $('resultBtn').addEventListener('click', () => { $('resultOverlay').hidden = true; refreshPrinters(); });

    $('adminClose').addEventListener('click', () => { $('adminOverlay').hidden = true; });
    $('adminTokenForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = $('adminLoginBtn');
      btn.disabled = true;
      try {
        const { status, data } = await getJSON('/api/admin/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ login: $('adminLogin').value.trim(), password: $('adminToken').value }),
        }).catch(() => ({ status: 0, data: {} }));
        if (!data.success) { toast(data.message || (status ? 'Kirib bo‘lmadi' : 'Server bilan aloqa yo‘q'), 'err'); $('adminToken').select(); return; }
        try { localStorage.setItem('PRINTCHI_ADMIN_LOGIN', $('adminLogin').value.trim()); } catch (er) { /* */ }
        $('adminToken').value = '';
        setAdminToken(data.token);
        await unlockAdmin(true);
      } finally { btn.disabled = false; }
    });
    $('adminLogout').addEventListener('click', () => { setAdminToken(''); showAdminLock(); });
    document.querySelectorAll('[data-admin-tab]').forEach((b) => b.addEventListener('click', () => setAdminTab(b.dataset.adminTab)));
    $('adminUpload').addEventListener('submit', adminUpload);
    $('adminList').addEventListener('click', (e) => { const b = e.target.closest('[data-del]'); if (b) adminDelete(b.dataset.del); });
    $('promoCreate').addEventListener('submit', createPromo);
    $('promoList').addEventListener('click', async (e) => {
      const c = e.target.closest('[data-copy]');
      if (c) { toast((await copyText(c.dataset.copy)) ? `${c.dataset.copy} nusxalandi` : c.dataset.copy); return; }
      const d = e.target.closest('[data-pdel]');
      if (d) deletePromo(d.dataset.pdel);
    });

    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      if (!$('adminOverlay').hidden) $('adminOverlay').hidden = true;
      else if (!$('resultOverlay').hidden) $('resultOverlay').hidden = true;
      else if (!$('payOverlay').hidden && S.lastStatus !== 'CLAIMED' && S.lastStatus !== 'PRINTING') cancelPay();
    });
  }

  // ── PWA: o'rnatish va oflayn qobiq ─────────────────────
  let installEvt = null;
  function setupPwa() {
    if ('serviceWorker' in navigator && location.protocol !== 'file:') {
      navigator.serviceWorker.register('sw.js').catch(() => { /* PWA ixtiyoriy */ });
    }
    const btn = $('installBtn');
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      installEvt = e;
      btn.hidden = false;
    });
    btn.addEventListener('click', async () => {
      if (!installEvt) return;
      installEvt.prompt();
      const { outcome } = await installEvt.userChoice.catch(() => ({}));
      installEvt = null;
      btn.hidden = true;
      if (outcome === 'accepted') toast('Printchi ilova sifatida o‘rnatildi');
    });
    window.addEventListener('appinstalled', () => { btn.hidden = true; });
  }

  // ── Ishga tushirish ─────────────────────────────────────
  async function init() {
    bind();
    setupPwa();
    if (new URLSearchParams(location.search).get('view') === 'templates') S.view = 'templates';
    render();
    if (location.hash === '#admin') openAdmin();
    try { if (AppConfig.fetchLatestLiveUrl && AppConfig.shouldDiscoverUrl()) await AppConfig.fetchLatestLiveUrl(); } catch (e) { /* */ }
    await Promise.all([loadHealth(), refreshPrinters(), loadTemplates()]);
    render();
    setInterval(refreshPrinters, 15000);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
