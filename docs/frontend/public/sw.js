/*
 * Revelator service worker.
 *
 * Deliberately minimal: its job is to make the site installable and to keep the
 * shell working on a flaky phone connection. It is NOT an offline mode for
 * scanning, because every scan is a live Gemini call.
 *
 * Caching rules, in priority order:
 *   /api/*, /download/*   never touched (always straight to the network)
 *   navigations           network-first, cached shell only as an offline fallback
 *   /assets/*             cache-first (Vite content-hashes these, so a given URL
 *                         is immutable and a new build produces new URLs)
 *   other same-origin GET stale-while-revalidate (icons, favicon, tutorial jpgs)
 *   cross-origin          ignored (Google Fonts falls back to the local stack)
 *
 * Bump CACHE_VERSION whenever this file changes so the activate step can drop
 * the previous caches.
 */

const CACHE_VERSION = 'v1';
const SHELL_CACHE = `revelator-shell-${CACHE_VERSION}`;
const ASSET_CACHE = `revelator-assets-${CACHE_VERSION}`;
const KEEP = [SHELL_CACHE, ASSET_CACHE];

// '/' is the app shell (index.html). The rest is what a cold offline launch
// needs to render something that looks like Revelator rather than a broken page.
const SHELL_URLS = [
  '/',
  '/manifest.json',
  '/favicon.svg',
  '/icon-192.png',
  '/icon-512.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      // Individual addAll failures would reject the whole install, so add each
      // URL on its own and tolerate misses.
      .then(cache => Promise.all(
        SHELL_URLS.map(url => cache.add(url).catch(() => null)),
      ))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k.startsWith('revelator-') && !KEEP.includes(k))
            .map(k => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  );
});

function isBypassed(url) {
  return url.pathname.startsWith('/api/')
      || url.pathname.startsWith('/download/');
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (isBypassed(url)) return;

  // Navigations: always try the network so a fresh deploy lands immediately.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then(res => {
          const copy = res.clone();
          caches.open(SHELL_CACHE).then(c => c.put('/', copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match('/', { ignoreSearch: true })
          .then(hit => hit || Response.error())),
    );
    return;
  }

  // Hashed build output: safe to serve from cache forever.
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(req).then(hit => hit || fetch(req).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(ASSET_CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      })),
    );
    return;
  }

  // Everything else: serve cache immediately, refresh it in the background.
  event.respondWith(
    caches.match(req).then(hit => {
      const network = fetch(req).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(ASSET_CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => hit || Response.error());
      return hit || network;
    }),
  );
});
