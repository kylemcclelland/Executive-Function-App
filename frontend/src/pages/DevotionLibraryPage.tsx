import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { Button } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { ApiError, api } from '../services/api'
import { durationLabel } from '../lib/devotions'
import type { DevotionBrief } from '../types/devotions'

/** A 404 on the list means this server has no devotions route at all (it predates them). That is a real fault, never an empty library. */
const unavailable = 'The Devotions service isn’t available on this server yet (404 Not Found). The server probably needs to be updated.'

export function DevotionLibraryPage() {
  const query = useQuery({ queryKey: ['devotions'], queryFn: () => api<DevotionBrief[]>('/devotions') })
  const devotions = query.data ?? []
  return <><PageHeader eyebrow="ORA ET LABORA" title="Devotions">Prayers and devotions, each shown in its own words with its source.</PageHeader>
    {query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error instanceof ApiError && query.error.status === 404 ? unavailable : query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></>
      : devotions.length === 0 ? <Empty title="No devotions have been added yet">This library will grow as prayers are carefully sourced and approved. <Link to="/devotions/preview">See how a devotion page will look</Link>.</Empty>
      : <ul className="devotion-list" aria-label="Devotions">{devotions.map(devotion => {
        const duration = durationLabel(devotion.estimated_minutes)
        return <li key={devotion.id}><Link className="devotion-card" to={`/devotions/${devotion.slug}`}>
          <span className="devotion-card-text"><span className="devotion-card-title">{devotion.title}</span>{devotion.subtitle && <span className="devotion-card-subtitle">{devotion.subtitle}</span>}{(devotion.category || duration) && <span className="devotion-card-meta">{devotion.category && <span>{devotion.category}</span>}{duration && <span>{duration}</span>}</span>}</span>
          {devotion.bookmarked && <Bookmark size={18} fill="currentColor" aria-label="Saved" />}
        </Link></li>
      })}</ul>}
  </>
}
