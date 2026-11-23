/* V2 moment: buyurtma cheki.
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
    const label = $('totalLabel').textContent;
    const counting = /Hisoblanmoqda/.test(label);
    const pagesMatch = label.match(/(\d+)\s*bet/);
    const thermal = pressed('data-printer')?.dataset.printer === 'thermal';
    const custom = pressed('data-range')?.dataset.range === 'custom';
    const color = pressed('data-color')?.dataset.color === 'color';
    const orient = pressed('data-orient')?.dataset.orient === 'landscape' ? 'albom' : 'kitob';
    const pages = counting ? 'sanalmoqda…' : (pagesMatch ? pagesMatch[1] : '?') + (custom ? ` (${$('rangeInput').value.trim() || '?'})` : ', hammasi');
    return [
      ['Fayl', file.textContent],
      ['Printer', thermal ? 'XP-58, chek 58 mm' : 'Canon, A4 lazer'],
      ['Betlar', pages],
      ['Format', `${orient}, ${color ? 'rangli' : 'oq-qora'}`],
      ['Nusxa', `× ${$('copiesOut').textContent}`],
      ['Narx', `${color ? 400 : 250} so‘m / bet`],
    ];
  }

  function render() {
    /* app.js "Hozirgi buyurtma:" deb yozib, ostidan xulosa chiqaradi; V2 da xulosa chekda */
    document.querySelectorAll('#chat .bubble.bot > span').forEach((sp) => {
      if (sp.textContent.trim() === 'Yangiladim. Hozirgi buyurtma:') sp.textContent = 'Yangiladim, chekka qarang.';
    });
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

  /* Landing tugmalari ilovaning o'z boshqaruvlarini chaqiradi */
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    if (b.dataset.act === 'pick') $('fileInput').click();
    if (b.dataset.act === 'templates' && $('viewTemplates').hidden) $('navBtn').click();
    if (matchMedia('(max-width: 1023px)').matches) $('app').scrollIntoView({ behavior: 'smooth' });
  });
})();
