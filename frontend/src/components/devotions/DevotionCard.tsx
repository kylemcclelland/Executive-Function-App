import { Link } from 'react-router-dom'
import { Bookmark, Clock } from 'lucide-react'
import { durationLabel } from '../../lib/devotions'
import type { DevotionBrief } from '../../types/devotions'

/** One published devotion in the library. The whole card is a single link, so it is one keyboard stop. */
export function DevotionCard({ devotion }: { devotion: DevotionBrief }) {
  const duration = durationLabel(devotion.estimated_minutes)
  return <Link className="devotion-card" to={`/devotions/${devotion.slug}`}>
    <span className="devotion-card-top">
      {devotion.category ? <span className="tag devotion-card-category">{devotion.category}</span> : <span />}
      {devotion.bookmarked && <Bookmark size={17} fill="currentColor" aria-label="Saved" />}
    </span>
    <span className="devotion-card-title">{devotion.title}</span>
    {devotion.subtitle && <span className="devotion-card-subtitle">{devotion.subtitle}</span>}
    {(duration || !devotion.has_text) && <span className="devotion-card-meta">
      {duration && <span className="devotion-card-duration"><Clock size={13} aria-hidden="true" />{duration}</span>}
      {!devotion.has_text && <span>Prayer text not yet published</span>}
    </span>}
  </Link>
}
