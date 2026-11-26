/* Buyurtma cheki (asosiy uslubning "moment"i).
   app.js ga tegmaydi: uning DOM'idan holatni o'qiydi va chek qatorlarini chiqaradi.
   Faqat qiymati o'zgargan qator qayta "bosiladi" (termal kallak chapdan o'ngga yuradi). */
(function () {
  const $ = (id) => document.getElementById(id);
  const pressed = (attr) => document.querySelector(`[${attr}][aria-pressed="true"]`);
  const lines = $('rLines');
  const prev = new Map();

  function read() {
    const file = document.querySelector('#chat .file-name');
    if (!file) return [['Fayl', 'kutilmoqda']];
    if (document.querySelector('#chat .file-bubble')?.dataset.kind === 'template') {
      const pagesT = ($('totalLabel').textContent.match(/(\d+)\s*bet/) || [, '1'])[1];
      const copiesT = $('copiesOut').value;
      const totalT = parseInt($('totalText').textContent.replace(/\D/g, ''), 10) || 0;
      const unitT = Math.round(totalT / Math.max(1, pagesT * copiesT));
      return [
        ['Shablon', file.textContent],
        ['Printer', 'Canon, A4 lazer'],
        ['Betlar', pagesT],
        ['Nusxa', `× ${copiesT}`],
        ['Narx', `${unitT} so‘m / bet`],
      ];
    }
    const label = $('totalLabel').textContent;
    const counting = /Hisoblanmoqda/.test(label);
    const pagesMatch = label.match(/(\d+)\s*bet/);
    const custom = pressed('data-range')?.dataset.range === 'custom';
    const orient = pressed('data-orient')?.dataset.orient === 'landscape' ? 'albom' : 'kitob';
    const pages = counting ? 'sanalmoqda…' : (pagesMatch ? pagesMatch[1] : '?') + (custom ? ` (${$('rangeInput').value.trim() || '?'})` : ', hammasi');
    return [
      ['Fayl', file.textContent],
      ['Printer', 'Canon, A4 lazer'],
      ['Betlar', pages],
      ['Format', `${orient}, oq-qora`],
      ['Nusxa', `× ${$('copiesOut').value}`],
      ['Narx', '250 so‘m / bet'],
    ];
  }

  function render() {
    const rows = read();
    const keys = rows.map((r) => r[0]).join('|');
    if (lines.dataset.keys !== keys) { lines.innerHTML = ''; lines.dataset.keys = keys; prev.clear(); }
    rows.forEach(([k, v], i) => {
      let row = lines.children[i];
      if (!row) {
        row = document.createElement('div');
        row.innerHTML = '<dt></dt><dd></dd>';
        row.firstChild.textContent = k;
        lines.appendChild(row);
      }
      if (prev.get(k) !== v) {
        row.lastChild.textContent = v;
        if (prev.has(k) || rows.length > 1) {
          row.classList.remove('printed'); void row.offsetWidth; row.classList.add('printed');
        }
        prev.set(k, v);
      }
    });
  }

  let queued = false;
  const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; render(); }); } };
  const mo = new MutationObserver(schedule);
  mo.observe($('chat'), { childList: true, subtree: true });
  mo.observe($('totalLabel'), { childList: true, characterData: true, subtree: true });
  mo.observe($('copiesOut'), { childList: true, characterData: true, subtree: true });
  mo.observe($('settingsGrid'), { attributes: true, attributeFilter: ['aria-pressed', 'hidden'], subtree: true });
  $('rangeInput').addEventListener('input', schedule);
  render();

  /* To'lov cheki: fayl bo'lsa ilova chekining qatorlari, shablon bo'lsa shablon qatorlari */
  const payLines = $('payLines');
  function renderPay() {
    const sum = $('paySummary').textContent;
    let rows;
    if (/^Shablon:/.test(sum)) {
      rows = read();
    } else if (/tayyorlanmoqda/.test(sum)) {
      rows = [['Holat', 'buyurtma yaratilmoqda…']];
    } else {
      rows = read();
      const m = sum.match(/^(\d+)\s*bet/);   // server qaytargan bet soni ustun
      if (m) rows = rows.map((r) => (r[0] === 'Betlar' ? ['Betlar', r[1].replace(/^(\d+|\?)/, m[1])] : r));
    }
    payLines.replaceChildren(...rows.map(([k, v]) => {
      const row = document.createElement('div');
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); dd.textContent = v;
      row.append(dt, dd);
      return row;
    }));
  }
  new MutationObserver(renderPay).observe($('paySummary'), { childList: true, characterData: true, subtree: true });
  renderPay();

  /* Rejim: asosiy light, tanlov eslab qolinadi */
  const root = document.documentElement;
  const themeBtn = $('themeBtn');
  function applyTheme(t) {
    root.dataset.theme = t;
    themeBtn.setAttribute('aria-pressed', String(t === 'dark'));
    themeBtn.setAttribute('aria-label', t === 'dark' ? 'Kunduzgi rejim' : 'Tungi rejim');
    $('themeColor').setAttribute('content', t === 'dark' ? '#0E0F11' : '#F3F4F1');
  }
  applyTheme(root.dataset.theme === 'dark' ? 'dark' : 'light');
  themeBtn.addEventListener('click', () => {
    const t = root.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(t);
    try { localStorage.setItem('printchi-theme', t); } catch (e) {}
  });

  /* Landing tugmalari ilovaning o'z boshqaruvlarini chaqiradi */
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    if (b.dataset.act === 'pick') $('fileInput').click();
    if (b.dataset.act === 'templates' && $('viewTemplates').hidden) $('navBtn').click();
    if (matchMedia('(max-width: 1023px)').matches) $('app').scrollIntoView({ behavior: 'smooth' });
  });
})();
