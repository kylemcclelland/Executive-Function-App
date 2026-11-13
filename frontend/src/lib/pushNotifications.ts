import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'

/** Browser push for Rule of Life reminders. Phase 1: a browser can subscribe and unsubscribe;
 * no reminder is actually sent yet (the Phase 2 delivery job does not exist). Permission is
 * only ever requested from a user gesture, never on load. */

export type PushConfig = { configured: boolean; public_key: string | null }
export type PushStatus = { configured: boolean; subscription_count: number; delivery: string }
export type PermissionState = 'unsupported' | 'default' | 'granted' | 'denied'

export const pushSupported = () =>
  typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

export const permissionState = (): PermissionState => (pushSupported() ? Notification.permission : 'unsupported')

export function usePushConfig() {
  return useQuery({ queryKey: ['push-config'], queryFn: () => api<PushConfig>('/push/config'), staleTime: 60 * 60 * 1000, retry: false })
}

export function usePushStatus() {
  return useQuery({ queryKey: ['push-status'], queryFn: () => api<PushStatus>('/push/status'), retry: false })
}

/** The browser's own subscription for our service worker, if any (asks the server nothing). */
export function useBrowserSubscription() {
  return useQuery({
    queryKey: ['push-browser-subscription'],
    queryFn: async () => {
      if (!pushSupported() || Notification.permission !== 'granted') return null
      const registration = await navigator.serviceWorker.getRegistration('/sw.js')
      return (await registration?.pushManager.getSubscription()) ?? null
    },
    retry: false,
  })
}

/** Decodes the base64url VAPID public key into the bytes PushManager.subscribe expects. */
export function applicationServerKey(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(base64url.length / 4) * 4, '=')
  return Uint8Array.from(atob(padded), char => char.charCodeAt(0))
}

async function registerWorker() {
  return navigator.serviceWorker.register('/sw.js', { scope: '/' })
}

/** Requests permission (must be called from a click), subscribes this browser and registers it
 * with the backend. Returns the resulting permission so the caller can explain a denial. */
export async function enablePushNotifications(publicKey: string): Promise<PermissionState> {
  if (!pushSupported()) return 'unsupported'
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return permission
  const registration = await registerWorker()
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: applicationServerKey(publicKey) as BufferSource }))
  const json = subscription.toJSON()
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) throw new Error('This browser produced an incomplete push subscription.')
  await api('/push/subscriptions', 'POST', { endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } })
  return 'granted'
}

/** Unsubscribes this browser and removes its registration from the backend. */
export async function disablePushNotifications(): Promise<void> {
  if (!pushSupported()) return
  const registration = await navigator.serviceWorker.getRegistration('/sw.js')
  const subscription = await registration?.pushManager.getSubscription()
  if (!subscription) return
  const endpoint = subscription.endpoint
  await subscription.unsubscribe()
  await api('/push/subscriptions', 'DELETE', { endpoint })
}

export function useRefreshPushState() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['push-status'] })
    void client.invalidateQueries({ queryKey: ['push-browser-subscription'] })
  }
}
