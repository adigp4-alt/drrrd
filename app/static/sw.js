/* ForesightTape service worker.
 *
 * Two different caching strategies, because the two kinds of request have
 * opposite requirements:
 *
 *   App shell (HTML, icons, manifest) — network-first with a cache fallback.
 *   Keeps the app current on every launch, but still opens instantly when the
 *   phone is offline or the free-tier host is asleep.
 *
 *   Forecast API — network-first, and a *successful* response is cached so the
 *   last good board survives going offline. Stale forecasts are clearly worse
 *   than none if they masquerade as fresh, so a cached API response is served
 *   with an `X-From-Cache` header and the page labels it as such rather than
 *   passing yesterday's probabilities off as today's.
 *
 * Never cache POSTs, and never cache an error response.
 */

const VERSION = "ft-v1";
const SHELL_CACHE = `${VERSION}-shell`;
const DATA_CACHE = `${VERSION}-data`;

const SHELL = [
  "/foresight",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      // addAll rejects the whole install if any single URL fails, which would
      // leave the app with no worker at all; tolerate individual misses.
      .then((cache) => Promise.allSettled(SHELL.map((u) => cache.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

function isForecastApi(url) {
  return url.pathname.startsWith("/foresight/api/");
}

async function networkFirst(request, cacheName, markStale) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (!cached) throw err;
    if (!markStale) return cached;
    // Flag served-from-cache so the UI can say the board is not live.
    const body = await cached.blob();
    const headers = new Headers(cached.headers);
    headers.set("X-From-Cache", "1");
    return new Response(body, {
      status: cached.status, statusText: cached.statusText, headers,
    });
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;            // never cache mutations

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // let CDNs handle themselves

  // Diagnostics must always reflect reality — a cached "healthy" verdict during
  // an outage would be actively misleading.
  if (url.pathname === "/foresight/api/diagnostics") return;

  if (isForecastApi(url)) {
    event.respondWith(networkFirst(request, DATA_CACHE, true));
    return;
  }
  if (request.mode === "navigate" || url.pathname.startsWith("/static/")) {
    event.respondWith(networkFirst(request, SHELL_CACHE, false));
  }
});
