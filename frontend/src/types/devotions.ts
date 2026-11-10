/**
 * One structure for every devotion, from a single prayer to a multi-step sequence. The same page
 * renders both; a simple prayer just has no steps. Instruction, commentary and prayer wording are
 * separate fields so they can never be mixed up on the page.
 *
 * Readers only ever receive published devotions and, within them, approved prayer texts. The
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

/** The exact approved wording of one prayer in one language. Latin and English share a `slot`. */
export interface PrayerText {
  id: string
  slot: string
  language: string
  title: string | null
  body: string
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

// ---- Editorial (private): everything, with its status ------------------------------------------
export type WorkflowStatus = 'proposed' | 'source_verified' | 'pending_approval' | 'approved' | 'published'
export type TextStatus = 'proposed' | 'source_verified' | 'pending_approval' | 'approved'
export type DecisionKind = 'return_for_research' | 'reject_text' | 'reject_approval' | 'withdraw'

export interface EditorialAccess { is_editor: boolean; is_approver: boolean }

export interface EditorialEvent {
  id: string
  text_id: string | null
  actor: string
  action: string
  from_status: string | null
  to_status: string | null
  note: string | null
  created_at: string
}

export interface TextSummary {
  slot: string
  language: string
  status: TextStatus
  license_status: LicenseStatus
  has_body: boolean
  source_verified: boolean
}

export interface EditorialBrief {
  id: string
  slug: string
  title: string
  category: string | null
  status: WorkflowStatus
  prose_origin: string | null
  texts: TextSummary[]
  texts_approved: number
  texts_total: number
  updated_at: string
}

export interface EditorialText {
  id: string
  devotion_slug: string
  slot: string
  language: string
  position: number
  title: string | null
  body: string
  has_body: boolean
  is_translation: boolean
  translator: string | null
  source_title: string | null
  source_authority: string | null
  source_edition: string | null
  source_date: string | null
  source_url: string | null
  source_retrieved_at: string | null
  attribution: string | null
  license_status: LicenseStatus
  license_notes: string | null
  rights_cleared: boolean
  status: TextStatus
  entered_by: string
  source_verified_by: string | null
  source_verified_at: string | null
  approved_by: string | null
  approved_at: string | null
  approval_current: boolean
  problems: string[]
  last_event: EditorialEvent | null
  updated_at: string
}

export interface EditorialDevotion {
  id: string
  slug: string
  title: string
  subtitle: string | null
  category: string | null
  estimated_minutes: number | null
  overview: string
  background: string | null
  significance: string | null
  references: SourceReference[]
  instructions: string[]
  steps: DevotionStep[]
  choice_label: string | null
  prose_origin: string | null
  status: WorkflowStatus
  created_by: string
  source_verified_by: string | null
  source_verified_at: string | null
  approved_by: string | null
  approved_at: string | null
  published_at: string | null
  approval_current: boolean
  problems: string[]
  publication_problems: string[]
  texts: EditorialText[]
  updated_at: string
}

/** A prayer text in the private preview: it says whether a reader would see it right now. */
export interface PreviewText extends PrayerText {
  status: TextStatus
  approval_current: boolean
  publicly_visible: boolean
  has_body: boolean
  rights_cleared: boolean
  license_notes: string | null
}

export interface EditorialPreview extends Devotion {
  texts: PreviewText[]
  devotion_status: WorkflowStatus
  /** "ai_draft" when the explanatory prose was drafted with AI assistance and is not yet approved. */
  prose_origin: string | null
}
