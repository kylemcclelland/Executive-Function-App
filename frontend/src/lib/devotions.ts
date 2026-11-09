import { useCallback, useState } from 'react'
import type { Devotion, LanguageChoice, LicenseStatus, PrayerText, TextSize } from '../types/devotions'

const LANGUAGE_NAMES: Record<string, string> = { en: 'English', la: 'Latin' }
/** Latin before English before anything else, so a bilingual pair always reads in the same order. */
const LANGUAGE_RANK: Record<string, number> = { la: 0, en: 1 }

export function languageLabel(code: string): string {
  if (LANGUAGE_NAMES[code]) return LANGUAGE_NAMES[code]
  try { return new Intl.DisplayNames(['en'], { type: 'language' }).of(code) ?? code } catch { return code }
}

export function sortLanguages(codes: string[]): string[] {
  return [...new Set(codes)].sort((a, b) => (LANGUAGE_RANK[a] ?? 9) - (LANGUAGE_RANK[b] ?? 9) || a.localeCompare(b))
}

export function availableLanguages(texts: PrayerText[]): string[] {
  return sortLanguages(texts.map(text => text.language))
}

/** The reader's preferred language, or the best available one when it is not offered here. */
export function resolveLanguage(preference: LanguageChoice, available: string[]): LanguageChoice {
  if (available.length === 0) return preference
  if (preference === 'both') return available.length > 1 ? 'both' : available[0]
  if (available.includes(preference)) return preference
  return available.includes('en') ? 'en' : available[0]
}

/** Slots in the order the prayer texts were given, each with its versions in reading order. */
export function groupBySlot(texts: PrayerText[]): { slot: string; versions: PrayerText[] }[] {
  const slots = new Map<string, PrayerText[]>()
  for (const text of texts) slots.set(text.slot, [...(slots.get(text.slot) ?? []), text])
  return [...slots].map(([slot, versions]) => ({ slot, versions: [...versions].sort((a, b) => (LANGUAGE_RANK[a.language] ?? 9) - (LANGUAGE_RANK[b.language] ?? 9) || a.language.localeCompare(b.language)) }))
}

/** The versions of one text to show for a language choice, with a note when the choice is not offered. */
export function versionsFor(versions: PrayerText[], choice: LanguageChoice): { shown: PrayerText[]; missing: string | null } {
  if (choice === 'both') return { shown: versions, missing: null }
  const match = versions.filter(version => version.language === choice)
  if (match.length) return { shown: match, missing: null }
  return { shown: versions.slice(0, 1), missing: choice }
}

/** Only web links are ever made clickable; anything else is shown as plain text. */
export function safeUrl(value: string | null): string | null {
  if (!value) return null
  try { const url = new URL(value); return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null } catch { return null }
}

export const licenseLabels: Record<LicenseStatus, string | null> = {
  unverified: null, public_domain: 'Public domain', licensed: 'Used under licence', permission_granted: 'Used with permission',
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
  const [language, setLanguageState] = useState<LanguageChoice>(() => stored(LANGUAGE_KEY) ?? 'en')
  const step = useCallback((direction: 1 | -1) => setSize(current => {
    const next = SIZES[Math.min(SIZES.length - 1, Math.max(0, SIZES.indexOf(current) + direction))]
    remember(SIZE_KEY, next)
    return next
  }), [])
  const setLanguage = useCallback((choice: LanguageChoice) => { remember(LANGUAGE_KEY, choice); setLanguageState(choice) }, [])
  return { size, larger: () => step(1), smaller: () => step(-1), canGrow: size !== 'xlarge', canShrink: size !== 'normal', language, setLanguage }
}
