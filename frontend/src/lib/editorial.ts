import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../services/api'

/** The owner-only editorial dashboard. Access is decided by the server (OWNER_CLERK_USER_ID);
 * the frontend only asks a light probe and fetches no draft data unless the probe says owner. */

export type EditorialText = {
  id: string; slot: string; language: string; title: string | null; body: string; status: string
  is_translation: boolean; translator: string | null; source_title: string | null; source_url: string | null
  attribution: string | null; license_status: string; license_notes: string | null
}
export type EditorialBrief = {
  slug: string; title: string; status: string; category: string | null; estimated_minutes: number | null
  languages: string[]; discovery: Record<string, unknown> | null; created_by: string; prose_origin: string | null
  published: boolean; updated_at: string | null; attribution: string | null; themes: string[]; tradition: string | null
}
export type EditorialDetail = EditorialBrief & {
  overview: string; background: string | null; significance: string | null
  references: { label: string; url: string | null }[]; instructions: string[]; steps: unknown[]
  texts: EditorialText[]
  events: { actor: string; action: string; from_status: string | null; to_status: string | null; note: string | null; at: string }[]
}

/** Whether this account is the owner, per the server. Only a 403 — the server's definitive
 * "signed in, but not the owner" — is cached as false. A 401 happens when the probe races
 * Clerk's token refresh just after sign-in (the sidebar mounts the moment auth loads), and a
 * network error says nothing about ownership: both are thrown so the query retries in a moment
 * and refetches on focus, instead of hiding the owner's navigation for ten minutes. */
export function useEditorialAccess() {
  return useQuery({
    queryKey: ['editorial-access'],
    queryFn: async () => {
      try { await api('/editorial/access'); return true } catch (error) {
        if (error instanceof ApiError && error.status === 403) return false
        throw error
      }
    },
    staleTime: 10 * 60 * 1000,
    // Only a 401 is retried: it is the token race, and a moment later the token exists. Anything
    // else (404 from an older backend, 5xx, network) fails once and refetches on focus as usual.
    retry: (failureCount, error) => failureCount < 3 && error instanceof ApiError && error.status === 401,
    retryDelay: attempt => Math.min(300 * 2 ** attempt, 2000),
  })
}

export function useEditorialQueue(enabled: boolean) {
  return useQuery({
    queryKey: ['editorial-queue'],
    queryFn: () => api<{ summary: Record<string, number>; devotions: EditorialBrief[] }>('/editorial/devotions'),
    enabled, retry: false,
  })
}

export function useEditorialDetail(slug: string | null) {
  return useQuery({
    queryKey: ['editorial-devotion', slug],
    queryFn: () => api<EditorialDetail>(`/editorial/devotions/${slug}`),
    enabled: slug !== null, retry: false,
  })
}

export function useEditorialAction() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ slug, action, textId }: { slug: string; action: string; textId?: string }) =>
      api(textId ? `/editorial/devotions/${slug}/texts/${textId}/${action}` : `/editorial/devotions/${slug}/${action}`, 'POST'),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['editorial-queue'] })
      void client.invalidateQueries({ queryKey: ['editorial-devotion'] })
      void client.invalidateQueries({ queryKey: ['devotions'] })
    },
  })
}

/** "About 1 minute" / "Approximately 3–5 minutes" from the stored numeric range. */
export function durationLabel(discovery: Record<string, unknown> | null, fallbackMinutes: number | null): string {
  const low = typeof discovery?.duration_min_minutes === 'number' ? discovery.duration_min_minutes : null
  const high = typeof discovery?.duration_max_minutes === 'number' ? discovery.duration_max_minutes : null
  if (low === null || high === null) return fallbackMinutes ? `About ${fallbackMinutes} minute${fallbackMinutes > 1 ? 's' : ''}` : 'Duration unknown'
  if (high < 0.5) return 'Short invocation'
  const round = (v: number) => (v < 1 ? 1 : Math.round(v))
  return round(low) === round(high) ? `About ${round(high)} minute${round(high) > 1 ? 's' : ''}` : `Approximately ${round(low)}–${round(high)} minutes`
}

export const LANGUAGE_NAMES: Record<string, string> = { en: 'English', la: 'Latin', el: 'Greek', hy: 'Armenian' }
