import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Bookmark } from 'lucide-react'
import { useState } from 'react'
import { Button } from '../components/ui'
import { Empty, ErrorMessage, Loading } from '../components/common'
import { isResponseLine } from '../lib/devotions'
import { KIND_LABELS, OFFICE_VIEW_KEY, isOfficeView, longDate, savedTitle } from '../lib/divineOffice'
import { ApiError, api } from '../services/api'
import type { OfficeLine, OfficeView, SavedOfficeDetail } from '../types/divineOffice'
import '../components/devotions/divine-office.css'

function Lines({ lines, language }: { lines: OfficeLine[]; language: 'la' | 'en' }) {
  return <div className="office-column" lang={language}>{lines.map((line, index) => {
    const response = line.kind === 'versicle' || line.kind === 'response' || isResponseLine(line.label ?? '')
    return <p key={index} className={`office-line is-${line.kind}${response ? ' is-response' : ''}`}>{line.label && <span className="office-label">{line.label} </span>}{line.text}</p>
  })}</div>
}

/** A saved Office prayer, reopened from the server's snapshot (no engine needed). The text is exactly what was saved. */
export function SavedOfficePage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [view, setView] = useState<OfficeView>(() => { try { const saved = window.localStorage.getItem(OFFICE_VIEW_KEY); return isOfficeView(saved) ? saved : 'english' } catch { return 'english' } })
  const query = useQuery({ queryKey: ['office-saved', id], queryFn: () => api<SavedOfficeDetail>(`/divine-office/saved/${encodeURIComponent(id)}`), retry: false })
  const remove = useMutation({
    mutationFn: () => api(`/divine-office/saved/${encodeURIComponent(id)}`, 'DELETE'),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['office-saved'] }); navigate('/devotions') },
  })
  if (query.isPending) return <Loading />
  if (query.isError) {
    return query.error instanceof ApiError && query.error.status === 404
      ? <Empty title="This saved prayer isn’t available">It may have been removed. <Link to="/devotions">Back to The Oratory</Link>.</Empty>
      : <ErrorMessage message={query.error.message} />
  }
  const item = query.data
  const date = longDate(item.source_date)
  const link = `/divine-office?date=${item.source_date}&hour=${item.source_hour}`
  return <article className="office" aria-labelledby="saved-office-title">
    <header className="office-header">
      <Link to="/devotions" className="devotion-back"><ArrowLeft size={16} aria-hidden="true" /> The Oratory</Link>
      <h1 id="saved-office-title">{savedTitle(item)}</h1>
      {item.title_english && item.title_latin && item.title_latin !== item.title_english && <p className="office-subtitle" lang="la">{item.title_latin}</p>}
      <p className="office-meta">{KIND_LABELS[item.kind] ?? item.kind} · Divine Office · {item.source_hour_name} · {date}{item.date_specific ? ' (belongs to this day)' : ' (first saved from this hour)'}</p>
      <div className="office-view" role="group" aria-label="Language">
        {([['english', 'English'], ['latin', 'Latin'], ['both', 'Side by side']] as const).map(([key, label]) => <Button key={key} size="sm" variant={view === key ? 'secondary' : 'ghost'} aria-pressed={view === key} onClick={() => setView(key)}>{label}</Button>)}
      </div>
    </header>
    <section className="office-section" aria-label="Saved prayer">
      {view === 'both'
        ? <div className="office-pair"><Lines lines={item.latin} language="la" /><Lines lines={item.english} language="en" /></div>
        : <Lines lines={view === 'latin' ? item.latin : item.english} language={view === 'latin' ? 'la' : 'en'} />}
    </section>
    <p><Link className="office-link" to={link}>Open this hour in the Office</Link></p>
    <div><Button variant="outline" disabled={remove.isPending} onClick={() => remove.mutate()}><Bookmark size={16} aria-hidden="true" /> Remove from Saved Prayers</Button></div>
    {remove.isError && <ErrorMessage message={remove.error.message} />}
    <footer className="office-source">
      <p><strong>Source.</strong> <a href={item.source.url} target="_blank" rel="noopener noreferrer">{item.source.name}</a>, version “{item.source.version}”{item.source.commit ? `, commit ${item.source.commit.slice(0, 10)}` : ''}. Software licence: {item.source.code_license}.</p>
      <p className="muted">{item.source.texts}</p>
    </footer>
  </article>
}
