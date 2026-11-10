/**
 * One structure for every devotion, from a single prayer to a multi-step sequence. The same page
 * renders both; a simple prayer just has no steps. Instruction, commentary and prayer wording are
 * separate fields so they can never be mixed up on the page.
 *
 * Every devotion and every prayer text held is shown. The
 * wording is shown exactly as received and is never generated, edited or reformatted here.
 */
export type LicenseStatus = 'unverified' | 'restricted' | 'public_domain' | 'licensed' | 'permission_granted'

/** Where a prayer text came from. Shown with the text, always. */
export interface TextSource {
  title: string | null
  authority?: string | null
  edition: string | null
  date?: string | null
  translator: string | null
  is_translation: boolean
  attribution: string | null
  url: string | null
  license_status: LicenseStatus
}

/** The exact wording of one prayer in one language (or a citation only, when `has_wording` is false). Latin and English share a `slot`. */
export interface PrayerText {
  id: string
  slot: string
  language: string
  title: string | null
  body: string
  /** False for a record that keeps only a citation: no wording is held for it. */
  has_wording?: boolean
  /** The devotion that holds this text: a step may reuse a prayer kept in another devotion. */
  devotion_slug?: string
  source: TextSource
}

export type StepKind = 'instruction' | 'prayer' | 'response'

/** One place in a sequence: structure and instruction only. A prayer step names its text by `text_slot`. */
export interface DevotionStep {
  kind: StepKind
  title: string | null
  instruction: string | null
  text_slot: string | null
  /** Set when the prayer is kept in another devotion and reused here. */
  devotion_slug?: string | null
  repeat: number | null
  section: string | null
  /** Steps of one group are alternatives the reader chooses between (a set of mysteries). */
  group?: string | null
  /** A traditional custom rather than a core element. */
  optional?: boolean
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
  /** Names the choice when steps are grouped (the Rosary's "Mysteries"). */
  choice_label?: string | null
  texts: PrayerText[]
}

export type TextSize = 'normal' | 'large' | 'xlarge'
/** A language code from the supported languages. */
export type LanguageChoice = string
