/* Dizayn laboratoriyasi uchun soxta backend: server yo'q bo'lsa ham variantlar
   "printer tayyor" holatida, haqiqiy shablon ro'yxati bilan ko'rinadi.
   Faqat design-lab/ sahifalarida yuklanadi — public/ ga ta'sir qilmaydi. */
(function () {
  const realFetch = window.fetch.bind(window);
  const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  let templates = null;
  async function loadTemplates() {
    if (templates) return templates;
    try { templates = await (await realFetch('../../template_data/templates.json')).json(); } catch (e) { templates = []; }
    return templates;
  }
  window.fetch = async function (input, opts) {
    const url = typeof input === 'string' ? input : input.url;
    const i = url.indexOf('/api/');
    if (i === -1) return realFetch(input, opts);
    const path = url.slice(i);
    await new Promise((r) => setTimeout(r, 250));
    if (path.startsWith('/api/printers')) return json({ printers: [
      { type: 'laser_bw', name: 'Canon LBP3010', connected: true, ready: true },
      { type: 'thermal', name: 'XP-58', connected: true, ready: true },
    ] });
    if (path.startsWith('/api/health')) return json({ status: 'ok', price_bw: 250, price_color: 400 });
    if (path.startsWith('/api/templates')) return json({ templates: await loadTemplates() });
    if (path.startsWith('/api/inspect-file')) return json({ success: true, page_count: 12 });
    if (path.startsWith('/api/order/create')) {
      const fd = opts && opts.body instanceof FormData ? opts.body : new FormData();
      const copies = Math.max(1, parseInt(fd.get('copies') || '1', 10));
      let pages = 1;
      if (fd.get('source') !== 'template') {
        pages = 12;                                   // inspect-file mock bilan bir xil
        const r = (fd.get('page_ranges') || '').trim();
        if (r) pages = r.split(',').reduce((n, part) => {
          const [a, b] = part.split('-').map(Number);
          return n + (b ? Math.max(0, b - a + 1) : (a ? 1 : 0));
        }, 0) || 1;
      }
      const unit = fd.get('color_mode') === 'color' ? 400 : 250;
      return json({ success: true, order_id: 'K7Q2M9', amount: pages * copies * unit, pages, payment: {
        qrData: 'demo', cardPretty: '5614 •••• •••• 0424', holder: 'Demo karta', bank: 'Humo' } });
    }
    return json({ success: false, error: 'demo' }, 404);
  };
})();
