import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bookmark, Cross, PenLine, Search, X } from 'lucide-react'
import { Button, Input } from '../components/ui'
import { Empty, ErrorMessage, Loading } from '../components/common'
import { DevotionCard } from '../components/devotions/DevotionCard'
import { api } from '../services/api'
import { useEditorialAccess } from '../lib/editorial'
import { LIBRARY_CATEGORIES, categoryKeyOf, categoryLabel, describeLibraryError, isCategoryKey, matchesSearch, type CategoryKey } from '../lib/devotions'
import type { DevotionBrief } from '../types/devotions'
import '../components/devotions/oratory.css'

const plural = (count: number) => `${count} ${count === 1 ? 'devotion' : 'devotions'}`

function Cards({ devotions, label }: { devotions: DevotionBrief[]; label: string }) {
  return <ul className="devotion-list" aria-label={label}>{devotions.map(devotion => <li key={devotion.id}><DevotionCard devotion={devotion} /></li>)}</ul>
}

/** The Oratory: browse, search and filter the published devotions already held in one list (no request per keystroke). */
export function DevotionLibraryPage() {
  const query = useQuery({ queryKey: ['devotions'], queryFn: () => api<DevotionBrief[]>('/devotions') })
  const access = useEditorialAccess()
  const isEditorial = !!access.data && (access.data.is_editor || access.data.is_approver)
  const [params, setParams] = useSearchParams()
  const text = params.get('q') ?? ''
  const categoryParam = params.get('category')
  const category: CategoryKey | 'all' = isCategoryKey(categoryParam) ? categoryParam : 'all'
  const all = query.data
  const results = useMemo(() => (all ?? []).filter(devotion => (category === 'all' || categoryKeyOf(devotion.category) === category) && matchesSearch(devotion, text)), [all, category, text])
  const saved = useMemo(() => (all ?? []).filter(devotion => devotion.bookmarked), [all])

  // Filters live in the address, so Back from a devotion returns to the same view. Typing replaces rather than stacks history.
  function setFilters(next: { q?: string; category?: CategoryKey | 'all' }) {
    const merged = new URLSearchParams(params)
    if (next.q !== undefined) { if (next.q) merged.set('q', next.q); else merged.delete('q') }
    if (next.category !== undefined) { if (next.category === 'all') merged.delete('category'); else merged.set('category', next.category) }
    setParams(merged, { replace: true })
  }

  const hero = <section className="oratory-hero" aria-labelledby="oratory-title">
    <p className="eyebrow">ORA ET LABORA</p>
    <h1 id="oratory-title">The Oratory</h1>
    <p className="oratory-subtitle">Bring what weighs on your heart to God.</p>
    <span className="oratory-rule" aria-hidden="true"><Cross size={15} strokeWidth={1.5} /></span>
    {isEditorial && <Link className="oratory-editorial-link" to="/editorial/devotions"><PenLine size={15} aria-hidden="true" />Editorial review</Link>}
  </section>

  if (query.isPending) return <div className="oratory">{hero}<Loading /></div>
  if (query.isError) {
    const problem = describeLibraryError(query.error)
    return <div className="oratory">{hero}<div className="oratory-problem"><ErrorMessage message={problem.message} />{problem.kind !== 'forbidden' && <Button variant="outline" onClick={() => void query.refetch()}>Try again</Button>}</div></div>
  }

  const libraryEmpty = all!.length === 0
  const searching = text.trim() !== ''
  const filtered = searching || category !== 'all'
  const heading = category === 'all' ? 'All devotions' : categoryLabel(category)
  return <div className="oratory">
    {hero}
    <section className="oratory-tools" aria-label="Find a devotion">
      <div className="oratory-search" role="search">
        <Search size={18} aria-hidden="true" />
        <Input type="search" id="oratory-search" aria-label="Search devotions" placeholder="Search devotions" autoComplete="off" value={text}
          onChange={event => setFilters({ q: event.target.value })} onKeyDown={event => { if (event.key === 'Escape' && text) { event.preventDefault(); setFilters({ q: '' }) } }} />
        {text && <Button type="button" variant="ghost" size="icon" aria-label="Clear search" onClick={() => setFilters({ q: '' })}><X size={17} /></Button>}
      </div>
      <div className="oratory-categories" role="group" aria-label="Categories">
        {[{ key: 'all' as const, label: 'All Devotions' }, ...LIBRARY_CATEGORIES].map(item => <Button key={item.key} size="sm" variant={category === item.key ? 'default' : 'outline'} aria-pressed={category === item.key} onClick={() => setFilters({ category: item.key })}>{item.label}</Button>)}
      </div>
      <p className="oratory-status" role="status">{libraryEmpty ? '' : filtered ? `Showing ${plural(results.length)} of ${all!.length}` : plural(all!.length)}</p>
    </section>

    <section className="oratory-section oratory-saved" aria-labelledby="oratory-saved-title">
      <h2 id="oratory-saved-title">Saved devotions</h2>
      {saved.length > 0 ? <Cards devotions={saved} label="Saved devotions" /> : <div className="oratory-note"><Bookmark size={20} aria-hidden="true" /><p><strong>Nothing saved yet</strong>When you save a devotion, it will wait for you here.</p></div>}
    </section>

    <section className="oratory-section" aria-labelledby="oratory-results-title">
      <h2 id="oratory-results-title">{libraryEmpty ? 'The library' : heading}</h2>
      {libraryEmpty
        ? <Empty title="No devotions have been added yet">This library will grow as prayers are carefully sourced and approved. <Link to="/devotions/preview">See how a devotion page will look</Link>.</Empty>
        : results.length > 0 ? <Cards devotions={results} label={heading} />
        : <Empty title={searching ? `No devotions match “${text.trim()}”` : `Nothing in ${heading} yet`}>
          {searching ? `Try a different word${category === 'all' ? '' : `, or look beyond ${heading}`}.` : 'This category will fill as prayers are carefully sourced and approved.'}
          <span className="oratory-empty-actions">
            {searching && <Button variant="outline" size="sm" onClick={() => setFilters({ q: '' })}>Clear search</Button>}
            {category !== 'all' && <Button variant="outline" size="sm" onClick={() => setFilters({ category: 'all' })}>Show all devotions</Button>}
          </span>
        </Empty>}
    </section>
  </div>
}
