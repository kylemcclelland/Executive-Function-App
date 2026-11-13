/* Optima Pars service worker: Rule of Life push notifications plus safe static caching for the
   installed app. Caching covers ONLY versioned, shared, same-origin static files — the hashed
   /assets bundle, fonts and icons. It never touches /api/ (authenticated, per-user), navigations,
   or anything cross-origin, so no user data, draft devotion or API response ever enters a shared
   cache. Push payloads carry only a title, an optional body, a dedup tag and a same-origin path;
   anything malformed falls back to a generic reminder on the Rule of Life page. */

const STATIC_CACHE = 'optima-pars-static-v1'
const PRECACHE = ['/manifest.webmanifest', '/favicon.svg', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png']

self.addEventListener('install', event => {
  self.skipWaiting()
  event.waitUntil(caches.open(STATIC_CACHE).then(cache => cache.addAll(PRECACHE)).catch(() => {}))
})

self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('optima-pars-static-') && key !== STATIC_CACHE).map(key => caches.delete(key)))),
  ]))
})

/** Only immutable or versioned shared files are cacheable; never the API, never a navigation. */
function cacheablePath(pathname) {
  return pathname.startsWith('/assets/') || pathname.startsWith('/fonts/') || PRECACHE.includes(pathname)
}

self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/') || !cacheablePath(url.pathname)) return   // network only: auth, user data, pages
  event.respondWith(caches.open(STATIC_CACHE).then(async cache => {
    const cached = await cache.match(request)
    if (cached) return cached
    const response = await fetch(request)
    if (response.ok) cache.put(request, response.clone())
    return response
  }))
})

/** Only a same-origin path may be opened from a notification; anything else goes to the Rule of Life. */
function safePath(value) {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') ? value : '/rule-of-life'
}

self.addEventListener('push', event => {
  let data = {}
  try { data = event.data ? event.data.json() : {} } catch { /* not JSON: show the fallback */ }
  const title = typeof data.title === 'string' && data.title ? data.title.slice(0, 120) : 'Time to pray'
  event.waitUntil(self.registration.showNotification(title, {
    body: typeof data.body === 'string' ? data.body.slice(0, 240) : '',
    tag: typeof data.tag === 'string' && data.tag ? data.tag.slice(0, 120) : 'rule-of-life',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: safePath(data.url) },
  }))
})

self.addEventListener('notificationclick', event => {
  event.notification.close()
  const url = safePath(event.notification.data && event.notification.data.url)
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windows => {
    const open = windows.find(client => 'focus' in client)
    if (open) { open.navigate(url); return open.focus() }
    return self.clients.openWindow(url)
  }))
})
