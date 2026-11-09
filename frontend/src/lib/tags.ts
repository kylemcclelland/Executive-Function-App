export const MAX_TAGS = 20
const MAX_LENGTH = 50

/** Mirrors the server: trim, drop a leading #, collapse spaces, cap the length. Case is kept. */
export function normalizeTag(raw: string) {
  return raw.trim().replace(/^#+\s*/, '').replace(/\s+/g, ' ').trim().slice(0, MAX_LENGTH).trim()
}
