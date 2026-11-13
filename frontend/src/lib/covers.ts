/** A friendly sentence for when Open Library has asked us to wait or is having trouble. */
export function cooldownMessage(blockedUntil: string | null, retryAfterSeconds: number | null, reason: 'rate_limited' | 'unavailable' | null = 'rate_limited') {
  const base = reason === 'unavailable'
    ? 'Open Library is temporarily unavailable.'
    : 'Open Library asked us to slow down.'
  if (!blockedUntil || retryAfterSeconds === null) return `${base} Try again a little later.`
  const at = new Date(blockedUntil).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  const minutes = Math.ceil(retryAfterSeconds / 60)
  const wait = retryAfterSeconds <= 90 ? 'in about a minute' : minutes <= 120 ? `in about ${minutes} minutes` : `in about ${Math.round(minutes / 60)} ${Math.round(minutes / 60) === 1 ? 'hour' : 'hours'}`
  return `${base} You can try again ${wait} (around ${at}). Your library is unchanged.`
}

export const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError'

/**
 * True for Open Library cover URLs addressed by ISBN. Loading these images spends the same
 * shared rate-limit quota that cover enrichment needs, so for now they are shown as
 * placeholders instead of being fetched. The stored URL itself is untouched; covers addressed
 * by numeric cover ID (/b/id/…) are not rate limited and load normally.
 */
export const isQuotaBoundCoverUrl = (url: string | null) =>
  url !== null && url.startsWith('https://covers.openlibrary.org/b/isbn/')

/**
 * The generated clothbound covers: six muted cloth colours, warm ivory text (--cover-ink).
 * A book's colour is a stable FNV-1a hash of its id, so the same book keeps the same cover
 * across page loads and devices without any stored column.
 */
export const COVER_PALETTE = [
  '#29483A', // forest green
  '#63413B', // burgundy brown
  '#363E59', // muted navy
  '#465568', // slate blue
  '#525A3D', // dark olive
  '#776652', // warm taupe
] as const

export function coverColor(bookId: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < bookId.length; index++) {
    hash ^= bookId.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return COVER_PALETTE[(hash >>> 0) % COVER_PALETTE.length]
}
