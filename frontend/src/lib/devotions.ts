import { useCallback, useState } from 'react'
import { ApiError } from '../services/api'
import type { Devotion, DevotionBrief, DevotionStep, LanguageChoice, LicenseStatus, PrayerText, TextSize } from '../types/devotions'

// ---- Languages ---------------------------------------------------------------------------------
/**
 * The languages the devotional system supports. Adding a language later is one more entry here (and
 * texts in that language); the selector, the messages and the editorial review all follow from it.
 * Nothing is ever translated automatically: a language with no text for a prayer simply has none.
 */
export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'la', label: 'Latin' },
] as const
export const DEFAULT_LANGUAGE = 'en'

export const isSupportedLanguage = (code: string | null | undefined): code is string => SUPPORTED_LANGUAGES.some(language => language.code === code)

export function languageLabel(code: string): string {
  const known = SUPPORTED_LANGUAGES.find(language => language.code === code)
  if (known) return known.label
  try { return new Intl.DisplayNames(['en'], { type: 'language' }).of(code) ?? code } catch { return code }
}

/** Latin before English before anything else, so a bilingual pair always reads in the same order. */
const LANGUAGE_RANK: Record<string, number> = { la: 0, en: 1 }
const byLanguage = (a: { language: string }, b: { language: string }) => (LANGUAGE_RANK[a.language] ?? 9) - (LANGUAGE_RANK[b.language] ?? 9) || a.language.localeCompare(b.language)

export function sortLanguages(codes: string[]): string[] {
  return [...new Set(codes)].sort((a, b) => byLanguage({ language: a }, { language: b }))
}

/** The languages in which at least one of these texts exists. */
export function availableLanguages(texts: { language: string }[]): string[] {
  return sortLanguages(texts.map(text => text.language))
}

/** The reader's language: their choice if it is supported, otherwise the default. Never guessed from the texts. */
export function resolveLanguage(preference: LanguageChoice | null | undefined): LanguageChoice {
  return isSupportedLanguage(preference) ? preference : DEFAULT_LANGUAGE
}

// ---- Prayer texts and where steps find them ---------------------------------------------------
export interface TextGroup { key: string; slot: string; owner: string; versions: PrayerText[] }

const ownerOf = (text: { devotion_slug?: string }, devotion: { slug: string }) => text.devotion_slug ?? devotion.slug

/** The versions of each prayer (one per language), in the order the prayers were given. A reused prayer is its own group. */
export function groupTexts(devotion: { slug: string }, texts: PrayerText[]): TextGroup[] {
  const groups = new Map<string, TextGroup>()
  for (const text of texts) {
    const owner = ownerOf(text, devotion)
    const key = `${owner}/${text.slot}`
    const group = groups.get(key) ?? { key, slot: text.slot, owner, versions: [] }
    group.versions = [...group.versions, text].sort(byLanguage)
    groups.set(key, group)
  }
  return [...groups.values()]
}

/** Slots named collection-<prayer> hold a devotion's ordered collection of prayers (the Rosary's own prayers), apart from its steps. */
export const COLLECTION_PREFIX = 'collection-'
const inCollection = (text: PrayerText) => text.slot.startsWith(COLLECTION_PREFIX) && !text.devotion_slug

/** A devotion's collection of prayers, in the order given, and every other text. Nothing is dropped; each text is in exactly one list. */
export function splitCollection(devotion: { slug: string }, texts: PrayerText[]): { collection: TextGroup[]; rest: PrayerText[] } {
  return { collection: groupTexts(devotion, texts.filter(inCollection)), rest: texts.filter(text => !inCollection(text)) }
}

/** The key under which a prayer step's wording is held: its own devotion's slot, or a reused one's. */
export const stepTextKey = (devotion: { slug: string }, step: DevotionStep) => step.text_slot ? `${step.devotion_slug ?? devotion.slug}/${step.text_slot}` : null

/** A readable name for a prayer: the title of the first step that uses it. */
export function textGroupTitle(devotion: Devotion, group: TextGroup): string | null {
  return devotion.steps.find(step => stepTextKey(devotion, step) === group.key && step.title)?.title ?? null
}

/** The versions of one prayer to show for a language: exactly that language, or none. Never another language in its place. */
export function versionsFor(versions: PrayerText[], language: LanguageChoice): { shown: PrayerText[]; missing: string | null } {
  const match = versions.filter(version => version.language === language)
  return match.length ? { shown: match, missing: null } : { shown: [], missing: language }
}

// ---- Steps that the reader chooses between (the Rosary's sets of mysteries) -------------------
export const stepGroups = (steps: DevotionStep[]): string[] => [...new Set(steps.map(step => step.group).filter((group): group is string => !!group))]

/** The steps to walk through: everything common, plus the chosen group's own steps. */
export const visibleSteps = (steps: DevotionStep[], group: string | null): DevotionStep[] => steps.filter(step => !step.group || step.group === group)

// ---- Display helpers ------------------------------------------------------------------------------
/** Only web links are ever made clickable; anything else is shown as plain text. */
export function safeUrl(value: string | null | undefined): string | null {
  if (!value) return null
  try { const url = new URL(value); return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null } catch { return null }
}

export const licenseLabels: Record<LicenseStatus, string | null> = {
  unverified: null, restricted: null, public_domain: 'Public domain', licensed: 'Used under licence', permission_granted: 'Used with permission',
}

/** Rights wording for the editorial screens, where an unknown or restricted status must be stated, not hidden. */
export const rightsLabels: Record<LicenseStatus, string> = {
  unverified: 'Rights not yet checked', restricted: 'Rights not cleared: wording withheld', public_domain: 'Public domain', licensed: 'Licensed', permission_granted: 'Permission granted',
}

/** Versicle and response markers at the start of a line (℣ ℟ with or without a full stop, or V. / R.). Display styling only. */
export function isResponseLine(line: string): boolean {
  return /^(?:[℣℟]\.?|V\.|R\.)(?:\s|$)/.test(line)
}

export function paragraphs(value: string): string[] {
  return value.split(/\n\s*\n/).map(part => part.trim()).filter(Boolean)
}

export function durationLabel(minutes: number | null): string | null {
  if (!minutes) return null
  return minutes === 1 ? 'About 1 minute' : `About ${minutes} minutes`
}

export const hasHowToPray = (devotion: Devotion) => devotion.instructions.length > 0 || devotion.steps.length > 0

// ---- Reading preferences: how the page looks to this reader. Nothing about what they have prayed. ----
export const SIZE_KEY = 'optima-pars:prayer-text-size'
export const LANGUAGE_KEY = 'optima-pars:prayer-language'
const SIZES: TextSize[] = ['normal', 'large', 'xlarge']

function stored(key: string): string | null {
  try { return window.localStorage.getItem(key) } catch { return null }
}
function remember(key: string, value: string) {
  try { window.localStorage.setItem(key, value) } catch { /* private mode: the choice just lasts for this visit */ }
}

export function useReadingPreferences() {
  const [size, setSize] = useState<TextSize>(() => { const saved = stored(SIZE_KEY); return SIZES.includes(saved as TextSize) ? saved as TextSize : 'normal' })
  const [language, setLanguageState] = useState<LanguageChoice>(() => resolveLanguage(stored(LANGUAGE_KEY)))
  const step = useCallback((direction: 1 | -1) => setSize(current => {
    const next = SIZES[Math.min(SIZES.length - 1, Math.max(0, SIZES.indexOf(current) + direction))]
    remember(SIZE_KEY, next)
    return next
  }), [])
  const setLanguage = useCallback((choice: LanguageChoice) => { const next = resolveLanguage(choice); remember(LANGUAGE_KEY, next); setLanguageState(next) }, [])
  return { size, larger: () => step(1), smaller: () => step(-1), canGrow: size !== 'xlarge', canShrink: size !== 'normal', language, setLanguage }
}

// ---- Browsing the library (The Oratory) -------------------------------------------------------
export const LIBRARY_CATEGORIES = [
  { key: 'daily-prayer', label: 'Daily Prayer' },
  { key: 'our-lord', label: 'Our Lord' },
  { key: 'our-lady', label: 'Our Lady' },
  { key: 'saints', label: 'Saints' },
  { key: 'liturgical-seasons', label: 'Liturgical Seasons' },
  { key: 'other', label: 'Other' },
] as const
export type CategoryKey = typeof LIBRARY_CATEGORIES[number]['key']

/** Lower-case, accent-free, single-spaced: so "Pater", "pater " and "PÁTER" are the same search. */
export function normalizeText(value: string): string {
  return value.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim()
}

/** The library category a devotion's free-text category belongs under. Anything unrecognised, or absent, is Other. */
export function categoryKeyOf(category: string | null): CategoryKey {
  const wanted = normalizeText(category ?? '')
  return LIBRARY_CATEGORIES.find(item => normalizeText(item.label) === wanted)?.key ?? 'other'
}

export const categoryLabel = (key: CategoryKey) => LIBRARY_CATEGORIES.find(item => item.key === key)!.label

export function isCategoryKey(value: string | null): value is CategoryKey {
  return LIBRARY_CATEGORIES.some(item => item.key === value)
}

/** Every search word must appear in the title, the short description (subtitle) or the category. */
export function matchesSearch(devotion: DevotionBrief, query: string): boolean {
  const words = normalizeText(query).split(' ').filter(Boolean)
  if (words.length === 0) return true
  const haystack = normalizeText([devotion.title, devotion.subtitle, devotion.category].filter(Boolean).join(' '))
  return words.every(word => haystack.includes(word))
}

export type LibraryErrorKind = 'unauthenticated' | 'forbidden' | 'unavailable' | 'server' | 'network' | 'other'

/** Each failure is told apart: none of them may ever be mistaken for an empty library. */
export function describeLibraryError(error: unknown): { kind: LibraryErrorKind; message: string } {
  if (error instanceof ApiError) {
    if (error.status === 401) return { kind: 'unauthenticated', message: 'Your session couldn’t be verified. Please sign in again.' }
    if (error.status === 403) return { kind: 'forbidden', message: 'Your account doesn’t have access to the devotional library.' }
    if (error.status === 404) return { kind: 'unavailable', message: 'The devotional library isn’t available on this server yet (404 Not Found). The server probably needs to be updated.' }
    if (error.status >= 500) return { kind: 'server', message: `The devotional library is temporarily unavailable (server error ${error.status}). Please try again in a moment.` }
    return { kind: 'other', message: error.message }
  }
  return { kind: 'network', message: 'We couldn’t reach the server. Check your connection and try again.' }
}
