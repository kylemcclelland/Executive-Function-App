import { useState, type ReactNode } from 'react'
import { splitCollection, useReadingPreferences } from '../../lib/devotions'
import type { Devotion, PrayerText } from '../../types/devotions'
import { DevotionHeader, HowToPray, Overview, PrayerTextSection } from './DevotionSections'
import { PrayerCollection } from './PrayerCollection'
import { LanguageSelect } from './PrayerText'
import { PrayerMode } from './PrayerMode'
import './devotions.css'

interface DevotionViewProps {
  devotion: Devotion
  backTo?: string
  backLabel?: string
  banner?: ReactNode
  /** Labels the explanatory prose (used in the private preview, where it is not yet approved). */
  proseNote?: ReactNode
  /** A mark shown with each prayer text (used in the private preview to show its approval state). */
  textBadge?: (text: PrayerText) => ReactNode
  onToggleBookmark?: (next: boolean) => void
  bookmarkPending?: boolean
}

/**
 * The one page template for every devotion, whether a single prayer or a multi-step sequence.
 * Sections whose content is absent are not rendered; the prayer text section always is, showing a
 * placeholder until approved wording exists. The Language dropdown sits at the top, and the choice
 * is remembered. Nothing on this page records that anything was prayed.
 */
export function DevotionView({ devotion, backTo = '/devotions', backLabel, banner, proseNote, textBadge, onToggleBookmark, bookmarkPending }: DevotionViewProps) {
  const prefs = useReadingPreferences()
  const [praying, setPraying] = useState(false)
  const { collection, rest } = splitCollection(devotion, devotion.texts)
  return <article className="devotion" aria-labelledby="devotion-title">
    {banner}
    <DevotionHeader devotion={devotion} backTo={backTo} backLabel={backLabel} controls={devotion.texts.length > 0 ? <LanguageSelect value={prefs.language} onChange={prefs.setLanguage} /> : undefined} onToggleBookmark={onToggleBookmark} bookmarkPending={bookmarkPending} />
    <Overview devotion={devotion} proseNote={proseNote} />
    <HowToPray devotion={devotion} />
    {(rest.length > 0 || collection.length === 0) && <PrayerTextSection devotion={{ ...devotion, texts: rest }} prefs={prefs} onEnterPrayerMode={() => setPraying(true)} textBadge={textBadge} />}
    <PrayerCollection groups={collection} prefs={prefs} textBadge={textBadge} />
    {praying && <PrayerMode devotion={devotion} prefs={prefs} onClose={() => setPraying(false)} textBadge={textBadge} />}
  </article>
}
