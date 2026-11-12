/* dg-score service worker: makes dg-score.html (and any downloaded course pack file) available offline.
   - app shell + packs: stale-while-revalidate / cache-first
   - bump VERSION when dg-score.html changes in a way that must reach users immediately */
const VERSION = 'dg-score-v2';
const SHELL = ['./dg-score.html', './dg-score-sw.js'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  const isPack = url.pathname.endsWith('.dgpack');
  e.respondWith((async () => {
    const cache = await caches.open(VERSION);
    // navigations like dg-score.html?pack=... must hit the cached shell regardless of the query string
    const hit = await cache.match(req, { ignoreSearch: req.mode === 'navigate' });
    const net = fetch(req).then(r => { if (r.ok) cache.put(req, r.clone()); return r; }).catch(() => null);
    if (hit) { if (!isPack) e.waitUntil(net); return hit; }            // packs: cache-first (they are big and immutable)
    return (await net) || new Response('Offline and not cached', { status: 503 });
  })());
});
