/** Push notifications (Phase 1): permission states, safe service-worker behaviour, and the
 * honest "ready but not delivering" settings panel. The service worker file itself is loaded
 * and run against a stubbed `self`, so its push and click handling is tested as shipped. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import swSource from '../../public/sw.js?raw'
import { applicationServerKey, permissionState, pushSupported } from '../lib/pushNotifications'

afterEach(() => { vi.unstubAllGlobals() })

describe('push support and permission states', () => {
  it('reports unsupported when the browser has no service worker or Push API', () => {
    vi.stubGlobal('navigator', {})
    expect(pushSupported()).toBe(false)
    expect(permissionState()).toBe('unsupported')
  })

  it('reflects the browser permission when supported', () => {
    vi.stubGlobal('navigator', { serviceWorker: {} })
    vi.stubGlobal('PushManager', function () {})
    for (const state of ['default', 'granted', 'denied'] as const) {
      vi.stubGlobal('Notification', { permission: state })
      expect(permissionState()).toBe(state)
    }
  })

  it('decodes a base64url VAPID key into bytes for PushManager.subscribe', () => {
    const key = applicationServerKey('BAa-_b12')
    expect(key).toBeInstanceOf(Uint8Array)
    expect(key.length).toBe(6)
    expect(key[0]).toBe(0x04)
  })
})

type Handler = (event: any) => void

/** Runs public/sw.js against a stubbed `self` and returns its registered handlers. */
function loadServiceWorker() {
  const handlers: Record<string, Handler> = {}
  const shownNotifications: Array<{ title: string; options: any }> = []
  const self = {
    skipWaiting: vi.fn(),
    addEventListener: (name: string, handler: Handler) => { handlers[name] = handler },
    registration: { showNotification: (title: string, options: any) => { shownNotifications.push({ title, options }); return Promise.resolve() } },
    clients: { claim: vi.fn(), matchAll: vi.fn().mockResolvedValue([]), openWindow: vi.fn().mockResolvedValue(null) },
  }
  new Function('self', swSource)(self)
  return { handlers, shownNotifications, self }
}

describe('service worker', () => {
  it('shows a notification named after the prayer, with a dedup tag and a same-origin link', async () => {
    const { handlers, shownNotifications } = loadServiceWorker()
    const payload = { title: 'Compline', body: 'Time for Compline', tag: 'rule:compline:2026-11-11', url: '/divine-office?date=2026-11-11&hour=compline' }
    await handlers.push({ data: { json: () => payload }, waitUntil: (p: Promise<void>) => p })
    expect(shownNotifications).toHaveLength(1)
    expect(shownNotifications[0].title).toBe('Compline')
    expect(shownNotifications[0].options.tag).toBe('rule:compline:2026-11-11')
    expect(shownNotifications[0].options.data.url).toBe('/divine-office?date=2026-11-11&hour=compline')
  })

  it('never navigates off-origin: a hostile or malformed payload falls back to the Rule of Life', async () => {
    const { handlers, shownNotifications } = loadServiceWorker()
    for (const url of ['https://evil.example.com/', '//evil.example.com', 'javascript:alert(1)', 42]) {
      await handlers.push({ data: { json: () => ({ title: 'Prime', url }) }, waitUntil: (p: Promise<void>) => p })
    }
    for (const shown of shownNotifications) expect(shown.options.data.url).toBe('/rule-of-life')
  })

  it('shows a generic reminder when the payload is not JSON', async () => {
    const { handlers, shownNotifications } = loadServiceWorker()
    await handlers.push({ data: { json: () => { throw new Error('not json') } }, waitUntil: (p: Promise<void>) => p })
    expect(shownNotifications[0].title).toBe('Time to pray')
  })

  it('focuses an open window on click, navigating it to the prayer', async () => {
    const { handlers, self } = loadServiceWorker()
    const open = { focus: vi.fn().mockResolvedValue(undefined), navigate: vi.fn() }
    self.clients.matchAll.mockResolvedValue([open])
    await handlers.notificationclick({ notification: { close: vi.fn(), data: { url: '/rule-of-life' } }, waitUntil: (p: Promise<void>) => p })
    expect(open.navigate).toHaveBeenCalledWith('/rule-of-life')
    expect(open.focus).toHaveBeenCalled()
    expect(self.clients.openWindow).not.toHaveBeenCalled()
  })

  it('opens a new window on click when none is open', async () => {
    const { handlers, self } = loadServiceWorker()
    await handlers.notificationclick({ notification: { close: vi.fn(), data: { url: '/divine-office' } }, waitUntil: (p: Promise<void>) => p })
    expect(self.clients.openWindow).toHaveBeenCalledWith('/divine-office')
  })
})
