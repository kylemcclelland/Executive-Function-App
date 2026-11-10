import type { OfficeHour, OfficeView } from '../types/divineOffice'

/** The eight canonical hours in order. A hour marked unavailable is shown as forthcoming and never requested. */
export const OFFICE_HOURS: OfficeHour[] = [
  { slug: 'matins', name: 'Matins', latin: 'Matutinum', available: true },
  { slug: 'lauds', name: 'Lauds', latin: 'Laudes', available: true },
  { slug: 'prime', name: 'Prime', latin: 'Prima', available: true },
  { slug: 'terce', name: 'Terce', latin: 'Tertia', available: true },
  { slug: 'sext', name: 'Sext', latin: 'Sexta', available: true },
  { slug: 'none', name: 'None', latin: 'Nona', available: true },
  { slug: 'vespers', name: 'Vespers', latin: 'Vesperae', available: true },
  { slug: 'compline', name: 'Compline', latin: 'Completorium', available: true },
]
export const DEFAULT_HOUR = 'compline'
export const OFFICE_VIEW_KEY = 'optima-pars:office-view'

const pad = (value: number) => String(value).padStart(2, '0')

/** A calendar date as YYYY-MM-DD, in the reader's own time zone (not UTC). */
export function isoDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export const today = () => isoDate(new Date())

export function isValidIsoDate(value: string | null | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(year, month - 1, day)
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day
}

export function shiftDate(value: string, days: number): string {
  const [year, month, day] = value.split('-').map(Number)
  return isoDate(new Date(year, month - 1, day + days))
}

export function longDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
}

export function isOfficeView(value: string | null | undefined): value is OfficeView {
  return value === 'english' || value === 'latin' || value === 'both'
}

export const KIND_LABELS: Record<string, string> = { psalm: 'Psalm', canticle: 'Canticle', hymn: 'Hymn', antiphon: 'Antiphon' }

/** The title of a saveable unit in the language(s) being read. */
export function unitTitle(unit: { title_latin: string; title_english: string | null }, view: OfficeView): string {
  if (view === 'latin') return unit.title_latin || unit.title_english || ''
  if (view === 'english') return unit.title_english || unit.title_latin
  return unit.title_english || unit.title_latin
}

export function savedTitle(item: { title_latin: string; title_english: string | null }): string {
  return item.title_english || item.title_latin
}

