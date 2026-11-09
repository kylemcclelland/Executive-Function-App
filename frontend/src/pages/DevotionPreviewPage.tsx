import { useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { Button } from '../components/ui'
import { DevotionView } from '../components/devotions/DevotionView'
import { PLACEHOLDER_KINDS, isPlaceholderKind, placeholderDevotion, placeholderLabels } from '../lib/devotionPlaceholders'

/** Shows the devotion page template with clearly labelled placeholder text. Nothing here is real or stored. */
export function DevotionPreviewPage() {
  const { kind } = useParams()
  const [saved, setSaved] = useState(false)
  if (kind !== undefined && !isPlaceholderKind(kind)) return <Navigate to="/devotions/preview" replace />
  const current = kind ?? 'simple'
  const banner = <aside className="devotion-preview-banner" role="note">
    <strong>Layout preview.</strong> Everything on this page is placeholder text for checking the design. It is not a devotion, it is not stored anywhere, and it contains no real prayer.
    <nav className="devotion-preview-kinds" aria-label="Layout examples">{PLACEHOLDER_KINDS.map(option => <Button key={option} asChild size="sm" variant={option === current ? 'default' : 'outline'}><Link to={`/devotions/preview/${option}`} aria-current={option === current ? 'page' : undefined}>{placeholderLabels[option]}</Link></Button>)}</nav>
  </aside>
  return <DevotionView key={current} devotion={{ ...placeholderDevotion(current), bookmarked: saved }} banner={banner} onToggleBookmark={setSaved} />
}
