import { useState, type ReactNode } from 'react'
import { useReadingPreferences } from '../../lib/devotions'
import type { Devotion } from '../../types/devotions'
import { DevotionHeader, HowToPray, Overview, PrayerTextSection } from './DevotionSections'
import { PrayerMode } from './PrayerMode'
import './devotions.css'

/**
 * The one page template for every devotion, whether a single prayer or a multi-step sequence.
 * Sections whose content is absent are not rendered; the prayer text section always is, showing a
 * placeholder until approved wording exists. Nothing on this page records that anything was prayed.
 */
export function DevotionView({ devotion, backTo = '/devotions', banner, onToggleBookmark, bookmarkPending }: { devotion: Devotion; backTo?: string; banner?: ReactNode; onToggleBookmark?: (next: boolean) => void; bookmarkPending?: boolean }) {
  const prefs = useReadingPreferences()
  const [praying, setPraying] = useState(false)
  return <article className="devotion" aria-labelledby="devotion-title">
    {banner}
    <DevotionHeader devotion={devotion} backTo={backTo} onToggleBookmark={onToggleBookmark} bookmarkPending={bookmarkPending} />
    <Overview devotion={devotion} />
    <HowToPray devotion={devotion} />
    <PrayerTextSection devotion={devotion} prefs={prefs} onEnterPrayerMode={() => setPraying(true)} />
    {praying && <PrayerMode devotion={devotion} prefs={prefs} onClose={() => setPraying(false)} />}
  </article>
}
