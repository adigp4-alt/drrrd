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
 *   CDN assets (Bootstrap, Font Awesome, Google Fonts) — cache-first. These
 *   URLs are version-pinned and immutable, so the newest copy is never a
 *   concern and the network round trip is pure cost. Without this, an installed
 *   app launched offline renders a fully-styled forecast board under an
 *   unstyled bullet-list navbar, because the shared chrome is Bootstrap's.
 *
 * Never cache POSTs, and never cache an error response.
 */

const VERSION = "ft-v1";
const SHELL_CACHE = `${VERSION}-shell`;
const DATA_CACHE = `${VERSION}-data`;
const ASSET_CACHE = `${VERSION}-assets`;

// Only these hosts. An open-ended cross-origin cache would happily fill up with
// anything the page ever touches.
const ASSET_HOSTS = new Set([
  "cdn.jsdelivr.net",
  "cdnjs.cloudflare.com",
  "fonts.googleapis.com",
  "fonts.gstatic.com",
]);

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

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  // Cross-origin requests without CORS come back opaque (status 0, body
  // unreadable). They still render fine as stylesheets and fonts, and caching
  // them is the entire point here, so accept them alongside genuine 200s.
  if (response && (response.ok || response.type === "opaque")) {
    cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;            // never cache mutations

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    // Pinned, immutable CDN assets: serve from cache so an offline launch has
    // its stylesheets and fonts. Anything else cross-origin is left alone.
    if (ASSET_HOSTS.has(url.hostname)) {
      event.respondWith(cacheFirst(request, ASSET_CACHE));
    }
    return;
  }

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
