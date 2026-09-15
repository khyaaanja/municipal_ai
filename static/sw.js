const CACHE_VERSION = 'bhaktapur-v1';
const STATIC_CACHE = CACHE_VERSION + '-static';
const DYNAMIC_CACHE = CACHE_VERSION + '-dynamic';

const PRECACHE_URLS = [
  '/',
  '/attractions/',
  '/events/',
  '/chat/',
  '/complaint/',
  '/static/manifest.json',
];

// Install: precache key pages
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => cache.addAll(PRECACHE_URLS))
      .catch(() => {})
  );
  self.skipWaiting();
});

// Activate: remove old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== STATIC_CACHE && k !== DYNAMIC_CACHE).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch: network-first for API/chat, cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Skip non-GET and cross-origin
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;

  // Never cache API calls
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/chat/feedback')) return;

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/media/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).then(resp => {
        if (resp.ok) {
          caches.open(DYNAMIC_CACHE).then(cache => cache.put(event.request, resp.clone()));
        }
        return resp;
      }))
    );
    return;
  }

  // Navigation: network-first with offline fallback
  event.respondWith(
    fetch(event.request)
      .then(resp => {
        if (resp.ok) {
          caches.open(DYNAMIC_CACHE).then(cache => cache.put(event.request, resp.clone()));
        }
        return resp;
      })
      .catch(() => caches.match(event.request).then(cached => cached || caches.match('/')))
  );
});
