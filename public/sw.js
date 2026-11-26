/* Smart Printchi — service worker (PWA).
 * Sahifa va statik fayllar: avval tarmoqdan (har doim yangi versiya), tarmoq bo'lmasa — keshdan.
 * /api/ so'rovlari va boshqa domenlar keshlanmaydi: to'lov va printer holati doim jonli bo'lishi kerak.
 */
const CACHE = 'printchi-v1';
const SHELL = [
  './',
  'index.html',
  'styles.css?v=3.0.0',
  'config.js?v=3.0.0',
  'app.js?v=3.0.0',
  'receipt.js?v=3.0.0',
  'manifest.webmanifest',
  'icons/icon-192.png',
  'icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.includes('/api/')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(async () => {
        const hit = await caches.match(req, { ignoreSearch: req.mode === 'navigate' });
        if (hit) return hit;
        if (req.mode === 'navigate') return caches.match('index.html');
        return Response.error();
      }),
  );
});
