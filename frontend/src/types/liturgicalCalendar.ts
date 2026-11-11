/** The principal celebration of a date in the traditional (1960 Roman) calendar, from the Divinum Officium engine. */
export interface CalendarDay {
  date: string
  edition: string
  celebration: string
  celebration_latin: string
  /** Where the English name came from: the engine's own English, a fixed translation rule, or neither (the Latin is shown). */
  celebration_source: 'upstream_english' | 'translated' | 'latin_untranslated' | string
  /** Set when upstream's own English title was corrected by an exact-match rule. */
  english_correction?: string | null
  /** e.g. "Third Sunday of November (Breviary numbering)" for a resumed Epiphany Sunday: the Breviary's own count, not a civil date. */
  designation: string | null
  celebration_type: 'saint' | 'feast' | 'sunday' | 'feria' | 'temporal' | 'other' | string
  type_label: string
  qualifier: string | null
  rank: string | null
  rank_class: string | null
  rank_label: string | null
  season: string | null
  season_code: string | null
  commemorations: { latin: string; english: string | null }[]
  description: { text: string; source: { name: string; reference: string; note: string } } | null
  engine: { name: string; url: string; commit: string | null; version: string }
}
