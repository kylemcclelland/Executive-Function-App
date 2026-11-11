/** The Divine Office (Roman Breviary, Rubrics of 1960): what the server returns for one date and hour. Every word is the engine's. */
export type OfficeLineKind = 'text' | 'versicle' | 'response' | 'antiphon' | 'psalm_heading' | 'psalm_verse' | 'benediction' | 'rubric' | 'labelled'

export interface OfficeLine { kind: OfficeLineKind; text: string; label: string | null }
/** A navigable point inside a section (a nocturn, the Te Deum, a commemoration), found from the engine's own rubric lines. */
export interface OfficeMark { line: number; kind: 'nocturn' | 'te_deum' | 'commemoration' | string; latin: string; english: string | null }
/** One row pairs the Latin lines with the English lines the engine produced for the same place in the Office. */
export interface OfficeRow { latin: OfficeLine[]; english: OfficeLine[]; aligned: boolean; marks: OfficeMark[]; units?: OfficeUnit[] }
/** A complete prayer inside a row that can be saved (lines start..end-1 of both cells). Offered only where the server identified it reliably. */
export interface OfficeUnit { id: string; kind: 'psalm' | 'canticle' | 'hymn' | 'antiphon' | string; title_latin: string; title_english: string | null; start: number; end: number; date_specific: boolean }
export interface OfficeSection {
  id: string
  heading_latin: string | null
  heading_english: string | null
  note_latin: string | null
  note_english: string | null
  rows: OfficeRow[]
}
export interface OfficeSource { name: string; url: string; commit: string | null; version: string; code_license: string; texts: string }
export interface Office {
  date: string
  hour: string
  hour_name: string
  hour_latin: string
  liturgical_day: string | null
  liturgical_day_detail: string | null
  rank: string | null
  season: string | null
  season_code: string | null
  sections: OfficeSection[]
  source: OfficeSource
}
export interface OfficeHour { slug: string; name: string; latin: string; available: boolean }
export type OfficeView = 'english' | 'latin' | 'both'

/** A prayer the user saved from the Office (the server's snapshot; reopened without the engine). */
export interface SavedOfficeBrief {
  id: string
  unit_key: string
  kind: string
  title_latin: string
  title_english: string | null
  date_specific: boolean
  source_hour: string
  source_hour_name: string
  source_date: string
}
export interface SavedOfficeDetail extends SavedOfficeBrief { latin: OfficeLine[]; english: OfficeLine[]; source: OfficeSource }
