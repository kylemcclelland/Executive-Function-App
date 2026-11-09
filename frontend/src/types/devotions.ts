/**
 * One structure for every devotion, from a single prayer to a multi-step sequence. The same page
 * renders both; a simple prayer just has no steps. Instruction, commentary and prayer wording are
 * separate fields so they can never be mixed up on the page.
 *
 * Readers only ever receive published devotions and, within them, approved prayer texts. The
 * wording is shown exactly as received and is never generated, edited or reformatted here.
 */
export type LicenseStatus = 'unverified' | 'public_domain' | 'licensed' | 'permission_granted'

/** Where a prayer text came from. Shown with the text, always. */
export interface TextSource {
  title: string | null
  edition: string | null
  translator: string | null
  is_translation: boolean
  attribution: string | null
  url: string | null
  license_status: LicenseStatus
}

/** The exact approved wording of one prayer in one language. Latin and English share a `slot`. */
export interface PrayerText {
  id: string
  slot: string
  language: string
  title: string | null
  body: string
  source: TextSource
}

export type StepKind = 'instruction' | 'prayer' | 'response'

/** One place in a sequence: structure and instruction only. A prayer step names its text by `text_slot`. */
export interface DevotionStep {
  kind: StepKind
  title: string | null
  instruction: string | null
  text_slot: string | null
  repeat: number | null
  section: string | null
}

export interface SourceReference { label: string; url: string | null }

export interface DevotionBrief {
  id: string
  slug: string
  title: string
  subtitle: string | null
  category: string | null
  estimated_minutes: number | null
  bookmarked: boolean
  has_text: boolean
}

export interface Devotion extends DevotionBrief {
  overview: string
  background: string | null
  significance: string | null
  references: SourceReference[]
  /** The numbered "how to pray" guidance. Instruction, not prayer wording. */
  instructions: string[]
  steps: DevotionStep[]
  texts: PrayerText[]
}

export type TextSize = 'normal' | 'large' | 'xlarge'
/** A language code, or 'both' to show every available language together. */
export type LanguageChoice = string
