import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../components/ui'
import { Empty, ErrorMessage, Loading } from '../components/common'
import { EditorialGate } from '../components/editorial/EditorialGate'
import { StatusBadge } from '../components/editorial/EditorialParts'
import { api } from '../services/api'
import { LIBRARY_CATEGORIES, SUPPORTED_LANGUAGES, categoryKeyOf, categoryLabel, isCategoryKey, type CategoryKey } from '../lib/devotions'
import { WORKFLOW_ORDER, describeEditorialError, formatDate, languageSummary, rightsSummary, sourceSummary, workflowLabels, workflowTone } from '../lib/editorial'
import type { EditorialBrief, WorkflowStatus } from '../types/devotions'
import '../components/editorial/editorial.css'

const isStatus = (value: string | null): value is WorkflowStatus => WORKFLOW_ORDER.includes(value as WorkflowStatus)

function Queue() {
  const query = useQuery({ queryKey: ['editorial-devotions'], queryFn: () => api<EditorialBrief[]>('/editorial/devotions') })
  const [params, setParams] = useSearchParams()
  const statusParam = params.get('status')
  const categoryParam = params.get('category')
  const status = isStatus(statusParam) ? statusParam : 'all'
  const category: CategoryKey | 'all' = isCategoryKey(categoryParam) ? categoryParam : 'all'
  function setFilter(name: 'status' | 'category', value: string) {
    const next = new URLSearchParams(params)
    if (value === 'all') next.delete(name); else next.set(name, value)
    setParams(next, { replace: true })
  }
  if (query.isPending) return <Loading />
  if (query.isError) {
    const problem = describeEditorialError(query.error)
    return <div className="editorial-problem"><ErrorMessage message={problem.message} />{problem.kind !== 'forbidden' && <Button variant="outline" onClick={() => void query.refetch()}>Try again</Button>}</div>
  }
  const all = query.data
  const rows = all.filter(brief => (status === 'all' || brief.status === status) && (category === 'all' || categoryKeyOf(brief.category) === category))
  const filtering = status !== 'all' || category !== 'all'
  return <>
    <section className="editorial-filters" aria-label="Filter the review queue">
      <label><span>Workflow status</span><select value={status} onChange={event => setFilter('status', event.target.value)}><option value="all">All statuses</option>{WORKFLOW_ORDER.map(item => <option key={item} value={item}>{workflowLabels[item]}</option>)}</select></label>
      <label><span>Category</span><select value={category} onChange={event => setFilter('category', event.target.value)}><option value="all">All categories</option>{LIBRARY_CATEGORIES.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
      {filtering && <Button variant="ghost" size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</Button>}
      <p className="editorial-count" role="status">{all.length === 0 ? '' : filtering ? `Showing ${rows.length} of ${all.length}` : `${all.length} ${all.length === 1 ? 'devotion' : 'devotions'}`}</p>
    </section>
    {all.length === 0 ? <Empty title="The review queue is empty">No devotions have been added for review yet. Draft records are created by the seeding tool, never from this page.</Empty>
      : rows.length === 0 ? <Empty title="Nothing matches these filters">Try another status or category.<span className="oratory-empty-actions"><Button variant="outline" size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</Button></span></Empty>
      : <table className="review-queue">
        <caption className="sr-only">Devotions awaiting editorial review</caption>
        <thead><tr><th scope="col">Devotion</th><th scope="col">Category</th><th scope="col">Status</th>{SUPPORTED_LANGUAGES.map(language => <th key={language.code} scope="col">{language.label} text</th>)}<th scope="col">Source</th><th scope="col">Rights</th><th scope="col">Updated</th><th scope="col"><span className="sr-only">Review</span></th></tr></thead>
        <tbody>{rows.map(brief => {
          const source = sourceSummary(brief.texts)
          const rights = rightsSummary(brief.texts)
          return <tr key={brief.id}>
            <th scope="row" data-label="Devotion"><Link to={`/editorial/devotions/${brief.id}`}>{brief.title}</Link><small>{brief.slug}</small></th>
            <td data-label="Category">{brief.category ? categoryLabel(categoryKeyOf(brief.category)) : '—'}</td>
            <td data-label="Status"><StatusBadge label={workflowLabels[brief.status]} tone={workflowTone[brief.status]} /></td>
            {SUPPORTED_LANGUAGES.map(language => { const summary = languageSummary(brief, language.code); return <td key={language.code} data-label={`${language.label} text`}><StatusBadge label={summary.label} tone={summary.tone} detail={summary.detail} /></td> })}
            <td data-label="Source"><StatusBadge label={source.label} tone={source.tone} detail={source.detail} /></td>
            <td data-label="Rights"><StatusBadge label={rights.label} tone={rights.tone} detail={rights.detail} /></td>
            <td data-label="Updated">{formatDate(brief.updated_at)}</td>
            <td className="queue-action"><Button asChild size="sm" variant="outline"><Link to={`/editorial/devotions/${brief.id}`} aria-label={`Review ${brief.title}`}>Review</Link></Button></td>
          </tr>
        })}</tbody>
      </table>}
  </>
}

/** The private review queue: every proposed devotion, and where each language of it stands. */
export function EditorialQueuePage() {
  return <div className="editorial">
    <header className="editorial-hero"><p className="eyebrow">PRIVATE · EDITORS AND APPROVERS</p><h1>Editorial review</h1><p className="editorial-subtitle">Check each prayer against its source before it is shown. Nothing here is published until you approve it.</p></header>
    <EditorialGate>{() => <Queue />}</EditorialGate>
  </div>
}
