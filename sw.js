/* SafeNaksha service worker: network-first (always fresh data), cache fallback for offline.
   Only same-origin GET requests are handled; map tiles, CDN scripts and Nominatim pass through untouched. */
const CACHE = 'safenaksha-v1';
const SHELL = ['./', './index.html', './terms.html', './privacy.html', './disclaimer.html', './legal.css',
  './manifest.webmanifest', './assets/logo.svg', './assets/icon-192.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  if (u.pathname.endsWith('.pdf')) return; // large; never cache
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok) { const c = r.clone(); caches.open(CACHE).then(cc => cc.put(e.request, c)); }
    return r;
  }).catch(() => caches.match(e.request, {ignoreSearch: true}).then(r => r || caches.match('./index.html'))));
});
