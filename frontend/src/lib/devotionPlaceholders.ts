import type { Devotion, PrayerText, TextSource } from '../types/devotions'

/**
 * Layout placeholders for the page preview. They are labelled as such on screen, live only in this
 * file, are never stored or sent to the server, and contain no real prayer or devotional content.
 */
export const PLACEHOLDER_KINDS = ['simple', 'bilingual', 'sequence', 'minimal'] as const
export type PlaceholderKind = typeof PLACEHOLDER_KINDS[number]

export const placeholderLabels: Record<PlaceholderKind, string> = {
  simple: 'Simple prayer', bilingual: 'Latin and English', sequence: 'Multi-step devotion', minimal: 'Missing optional sections',
}

export const isPlaceholderKind = (value: string | undefined): value is PlaceholderKind => PLACEHOLDER_KINDS.includes(value as PlaceholderKind)

const source: TextSource = { title: 'Source title will appear here', edition: 'Edition will appear here', translator: null, is_translation: false, attribution: 'Attribution will appear here', url: null, license_status: 'unverified' }

const text = (slot: string, language: string, body: string, title: string | null = null): PrayerText => ({ id: `placeholder-${slot}-${language}`, slot, language, title, body, source })

const base: Devotion = {
  id: 'placeholder', slug: 'preview', title: 'Prayer Title', subtitle: 'Subtitle will appear here', category: 'Category', estimated_minutes: 10,
  bookmarked: false, has_text: true,
  overview: 'Overview will appear here.\n\nA second paragraph of the overview will appear here.',
  background: 'Historical background will appear here.', significance: 'Spiritual significance will appear here.',
  references: [{ label: 'Source reference will appear here', url: null }],
  instructions: ['Instructions will appear here.', 'A second numbered instruction will appear here.'],
  steps: [], texts: [text('main', 'en', 'Verified prayer text will appear here.\n\nA second paragraph of verified prayer text will appear here.')],
}

export function placeholderDevotion(kind: PlaceholderKind): Devotion {
  switch (kind) {
    case 'bilingual':
      return { ...base, texts: [text('main', 'en', 'Verified English text will appear here.\n\nA second paragraph will appear here.'), text('main', 'la', 'Verified Latin text will appear here.\n\nA second paragraph will appear here.')] }
    case 'sequence':
      return {
        ...base, title: 'Devotion Title', estimated_minutes: 20,
        instructions: ['Instructions for the whole devotion will appear here.'],
        steps: [
          { kind: 'instruction', title: null, instruction: 'Instruction for the opening will appear here.', text_slot: null, repeat: null, section: 'Opening' },
          { kind: 'prayer', title: 'Opening prayer', instruction: null, text_slot: 'opening', repeat: null, section: 'Opening' },
          { kind: 'prayer', title: 'Repeated prayer', instruction: 'A note about how to pray it will appear here.', text_slot: 'repeated', repeat: 10, section: 'Section 1' },
          { kind: 'response', title: 'Response', instruction: null, text_slot: 'response', repeat: null, section: 'Section 1' },
          { kind: 'prayer', title: 'Closing prayer', instruction: null, text_slot: 'closing', repeat: null, section: 'Closing' },
        ],
        // "closing" has no approved text, so its step shows the unpublished placeholder.
        texts: [
          text('opening', 'en', 'Verified opening text will appear here.'),
          text('repeated', 'en', 'Verified repeated text will appear here.'),
          text('response', 'en', '℣. Verified versicle will appear here.\n℟. Verified response will appear here.'),
        ],
      }
    case 'minimal':
      return { ...base, subtitle: null, category: null, estimated_minutes: null, background: null, significance: null, references: [], instructions: [], steps: [], texts: [], has_text: false }
    default:
      return base
  }
}
