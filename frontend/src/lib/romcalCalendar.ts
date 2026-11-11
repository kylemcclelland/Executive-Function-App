/**
 * The current (post-Vatican II) Roman calendar, calculated in the browser by Romcal with the United States propers. This module is the only place that
 * knows Romcal's shapes: everything else sees CurrentRomanDay. It shares nothing with the traditional (1960) calendar, whose celebrations, ranks and
 * seasons come from the Divinum Officium engine; the two are never mixed.
 */
import type { CalendarDay } from '../types/liturgicalCalendar'

export const ROMCAL_VERSION = '3.0.0-dev.144'
export const ROMCAL_SOURCE = { name: 'Romcal', version: ROMCAL_VERSION, url: 'https://github.com/romcal/romcal', calendar: 'General Roman Calendar with the United States propers' }

export type CurrentRank = 'solemnity' | 'feast' | 'memorial' | 'optional_memorial' | 'sunday' | 'feria' | 'other'

export interface CurrentRomanDay {
  date: string
  id: string
  name: string
  rank: CurrentRank
  rankLabel: string
  season: string | null
  color: string | null
  /** Where the celebration comes from in Romcal's calendars, e.g. "united_states" for a US proper or "general_roman". */
  calendarId: string | null
  optionalMemorials: { id: string; name: string }[]
}

/** The subset of Romcal's LiturgicalDay this module reads. */
interface RomcalDay {
  id: string
  name: string
  rank: string
  isOptional?: boolean
  colors?: string[]
  seasonNames?: string[]
  fromCalendarId?: string
}

const RANKS: Record<string, [CurrentRank, string]> = {
  SOLEMNITY: ['solemnity', 'Solemnity'],
  FEAST: ['feast', 'Feast'],
  MEMORIAL: ['memorial', 'Memorial'],
  OPTIONAL_MEMORIAL: ['optional_memorial', 'Optional Memorial'],
  SUNDAY: ['sunday', 'Sunday'],
  WEEKDAY: ['feria', 'Feria'],
}

const COLORS: Record<string, string> = { WHITE: 'White', RED: 'Red', GREEN: 'Green', PURPLE: 'Violet', ROSE: 'Rose', GOLD: 'Gold', BLACK: 'Black' }

/** Romcal's own days, by year, from one lazily loaded calendar: Romcal is loaded only when the Current Roman calendar is first shown. */
const years = new Map<number, Promise<Record<string, RomcalDay[]>>>()

function loadYear(year: number): Promise<Record<string, RomcalDay[]>> {
  let loaded = years.get(year)
  if (!loaded) {
    loaded = (async () => {
      const [{ Romcal }, { UnitedStates_En }] = await Promise.all([import('romcal'), import('@romcal/calendar.united-states')])
      return await new Romcal({ localizedCalendar: UnitedStates_En }).generateCalendar(year) as unknown as Record<string, RomcalDay[]>
    })()
    loaded.catch(() => years.delete(year))
    years.set(year, loaded)
  }
  return loaded
}

export function describeDay(date: string, entries: RomcalDay[]): CurrentRomanDay | null {
  const principal = entries.find(entry => !entry.isOptional) ?? entries[0]
  if (!principal) return null
  const [rank, rankLabel] = RANKS[principal.rank] ?? ['other', principal.rank.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())]
  const color = principal.colors?.[0]
  return {
    date, id: principal.id, name: principal.name, rank, rankLabel,
    season: principal.seasonNames?.[0] ?? null,
    color: color ? COLORS[color] ?? color.toLowerCase().replace(/^\w/, c => c.toUpperCase()) : null,
    calendarId: principal.fromCalendarId ?? null,
    optionalMemorials: entries.filter(entry => entry !== principal && entry.isOptional).map(entry => ({ id: entry.id, name: entry.name })),
  }
}

/** The principal celebration of an ISO date (YYYY-MM-DD, the reader's local date) in the current Roman calendar, or null if Romcal has none. */
export async function currentRomanDay(date: string): Promise<CurrentRomanDay | null> {
  const entries = (await loadYear(Number(date.slice(0, 4))))[date]
  return entries ? describeDay(date, entries) : null
}

// ---- Descriptions: reused from the traditional calendar only when both name the same saint ----
const ROLE_WORDS = new Set(['saint', 'saints', 'st', 'sts', 'pope', 'doctor', 'church', 'martyr', 'martyrs', 'bishop', 'confessor', 'virgin', 'virgins', 'abbot', 'priest', 'deacon', 'religious', 'founder', 'and', 'of', 'the', 'a', 'in', 'on'])

/** The significant name words of a celebration: lower-case, accents and Roman numerals dropped, without titles such as Saint, Pope or Martyr. */
export function nameTokens(name: string): string[] {
  return name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().split(/[^a-z]+/)
    .filter(word => word && !ROLE_WORDS.has(word) && !/^[ivxlc]+$/.test(word))
}

/**
 * The traditional description may be shown with a current celebration only when the two are the same saint: the same name words, never merely the same
 * date. Where the names differ (for example another saint was kept on that date in 1960), no description is shown.
 */
export function sameSaint(current: CurrentRomanDay, traditional: CalendarDay | undefined): boolean {
  if (!traditional?.description || traditional.celebration_type !== 'saint') return false
  if (current.rank === 'sunday' || current.rank === 'feria') return false
  const a = nameTokens(current.name)
  const b = nameTokens(traditional.celebration)
  return a.length > 0 && a.length === b.length && a.every(word => b.includes(word))
}
