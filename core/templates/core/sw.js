// Bhaktapur Municipal AI — Service Worker v{{ cache_version|default:1 }}
const CACHE_NAME = "shell-v{{ cache_version|default:1 }}";
const OFFLINE_URL = "{% url 'core:offline' %}";
const APP_SHELL = [
  "{% url 'core:home' %}",
  OFFLINE_URL,
  "/static/css/base.css",
  "/static/js/base.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "{% url 'core:web_manifest' %}",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin
  if (request.method !== "GET" || url.origin !== location.origin) return;

  // Never cache API calls (chat, scan, etc.)
  if (url.pathname.startsWith("/api/")) return;

  // HTML navigations: network-first with offline fallback
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((resp) => {
          caches.open(CACHE_NAME).then((c) => c.put(request, resp.clone()));
          return resp;
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match(OFFLINE_URL))
        )
    );
    return;
  }

  // Static assets: cache-first
  if (request.destination in { style: 1, script: 1, image: 1, font: 1 }) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request))
    );
    return;
  }

  // Everything else: network-first, cache fallback
  event.respondWith(
    fetch(request)
      .then((resp) => {
        caches.open(CACHE_NAME).then((c) => c.put(request, resp.clone()));
        return resp;
      })
      .catch(() => caches.match(request))
  );
});

