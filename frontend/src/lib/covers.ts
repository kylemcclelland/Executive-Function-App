/** A friendly sentence for when Open Library has asked us to wait. */
export function cooldownMessage(blockedUntil: string | null, retryAfterSeconds: number | null) {
  const base = 'Open Library asked us to slow down.'
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
