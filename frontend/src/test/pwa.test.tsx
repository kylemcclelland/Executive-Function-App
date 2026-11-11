/** PWA foundation: a valid installable manifest, the head tags installation needs, and a service
 * worker whose static caching can never capture the API, user data or anything cross-origin. The
 * push handlers' behaviour is covered separately in pushNotifications.test.tsx. */
import { describe, expect, it, vi } from 'vitest'
import manifestRaw from '../../public/manifest.webmanifest?raw'
import html from '../../index.html?raw'
import mainSource from '../main.tsx?raw'
import swSource from '../../public/sw.js?raw'

describe('the web app manifest', () => {
  const manifest = JSON.parse(manifestRaw)
  it('is installable: identity, standalone display and both required icon sizes', () => {
    expect(manifest.id).toBe('/')
    expect(manifest.name).toBe('Optima Pars')
    expect(manifest.short_name.length).toBeLessThanOrEqual(12)
    expect(manifest.display).toBe('standalone')
    expect(manifest.start_url).toBe('/')
    expect(manifest.scope).toBe('/')
    const sizes = manifest.icons.map((icon: { sizes: string }) => icon.sizes)
    expect(sizes).toContain('192x192')
    expect(sizes).toContain('512x512')
  })
  it('keeps the Optima Pars brand colors (ivory background, forest-green theme)', () => {
    expect(manifest.background_color).toBe('#F7F3EA')
    expect(manifest.theme_color).toBe('#355740')
  })
})

describe('the document head', () => {
  it('links the manifest and carries the mobile/standalone metas', () => {
    expect(html).toContain('rel="manifest" href="/manifest.webmanifest"')
    expect(html).toContain('name="viewport" content="width=device-width, initial-scale=1.0"')
    expect(html).toContain('name="mobile-web-app-capable" content="yes"')
    expect(html).toContain('name="apple-mobile-web-app-capable" content="yes"')
    expect(html).toContain('name="apple-mobile-web-app-title" content="Optima Pars"')
    expect(html).toContain('rel="apple-touch-icon"')
    expect(html).toContain('name="theme-color"')
  })
  it('registers the service worker on load, guarded by support', () => {
    expect(mainSource).toContain("'serviceWorker' in navigator")
    expect(mainSource).toContain("navigator.serviceWorker.register('/sw.js', { scope: '/' })")
  })
})

type Handler = (event: any) => void

function loadWorker() {
  const handlers: Record<string, Handler> = {}
  const stores = new Map<string, Map<string, { ok: boolean; clone: () => unknown }>>()
  const openCalls: string[] = []
  const cachesStub = {
    open: async (name: string) => {
      openCalls.push(name)
      if (!stores.has(name)) stores.set(name, new Map())
      const store = stores.get(name)!
      return {
        addAll: vi.fn(async (paths: string[]) => { for (const path of paths) store.set(path, { ok: true, clone: () => ({}) }) }),
        match: async (request: { url: string }) => store.get(new URL(request.url).pathname),
        put: async (request: { url: string }, response: unknown) => { store.set(new URL(request.url).pathname, response as never) },
      }
    },
    keys: async () => [...stores.keys()],
    delete: vi.fn(async (name: string) => stores.delete(name)),
  }
  const fetchStub = vi.fn(async () => ({ ok: true, clone: () => ({ cloned: true }) }))
  const self = {
    skipWaiting: vi.fn(),
    location: { origin: 'https://optima.test' },
    addEventListener: (name: string, handler: Handler) => { handlers[name] = handler },
    registration: { showNotification: vi.fn().mockResolvedValue(undefined) },
    clients: { claim: vi.fn().mockResolvedValue(undefined), matchAll: vi.fn().mockResolvedValue([]), openWindow: vi.fn() },
  }
  new Function('self', 'caches', 'fetch', swSource)(self, cachesStub, fetchStub)
  const dispatch = async (url: string, method = 'GET') => {
    const responded: unknown[] = []
    await handlers.fetch({ request: { url, method }, respondWith: (p: Promise<unknown>) => { responded.push(p) } })
    if (responded.length) await responded[0]
    return responded.length > 0
  }
  return { handlers, stores, cachesStub, fetchStub, self, dispatch }
}

describe('the service worker', () => {
  it('still registers the push and notification-click handlers alongside caching', () => {
    const { handlers } = loadWorker()
    for (const name of ['install', 'activate', 'fetch', 'push', 'notificationclick']) expect(handlers[name], name).toBeTypeOf('function')
  })

  it('precaches only the small shared shell on install and drops old caches on activate', async () => {
    const { handlers, stores, cachesStub } = loadWorker()
    stores.set('optima-pars-static-v0', new Map())
    await handlers.install({ waitUntil: (p: Promise<unknown>) => p })
    expect([...stores.get('optima-pars-static-v1')!.keys()]).toEqual(['/manifest.webmanifest', '/favicon.svg', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png'])
    await handlers.activate({ waitUntil: (p: Promise<unknown>) => p })
    expect(cachesStub.delete).toHaveBeenCalledWith('optima-pars-static-v0')
    expect(stores.has('optima-pars-static-v1')).toBe(true)
  })

  it('serves hashed assets cache-first: one network fetch, then the cache answers', async () => {
    const { dispatch, fetchStub } = loadWorker()
    expect(await dispatch('https://optima.test/assets/index-ab12cd.js')).toBe(true)
    expect(await dispatch('https://optima.test/assets/index-ab12cd.js')).toBe(true)
    expect(fetchStub).toHaveBeenCalledTimes(1)
  })

  it('never caches the API, navigations, other-origin requests or non-GET methods', async () => {
    const { dispatch, fetchStub } = loadWorker()
    expect(await dispatch('https://optima.test/api/devotions')).toBe(false)                 // authenticated, per-user
    expect(await dispatch('https://optima.test/api/editorial/devotions')).toBe(false)       // unpublished drafts
    expect(await dispatch('https://optima.test/rule-of-life')).toBe(false)                  // navigations stay network
    expect(await dispatch('https://evil.example.com/assets/app.js')).toBe(false)            // other origins untouched
    expect(await dispatch('https://optima.test/assets/app.js', 'POST')).toBe(false)
    expect(fetchStub).not.toHaveBeenCalled()
  })
})
