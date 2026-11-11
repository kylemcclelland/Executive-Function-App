import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BookOpenCheck, ChevronLeft, ChevronRight, ShieldAlert } from 'lucide-react'
import { Button, Card } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import {
  LANGUAGE_NAMES, durationLabel, useEditorialAccess, useEditorialAction, useEditorialDetail, useEditorialQueue,
} from '../lib/editorial'
import type { EditorialDetail } from '../lib/editorial'

const STATUS_LABELS: Record<string, string> = { proposed: 'Awaiting review', source_verified: 'Source verified', pending_approval: 'Pending approval', approved: 'Approved', published: 'Published' }
const DEVOTION_ACTIONS: Record<string, { action: string; label: string }> = {
  proposed: { action: 'verify-source', label: 'Mark sources verified' },
  source_verified: { action: 'approve', label: 'Approve devotion' },
  approved: { action: 'publish', label: 'Publish to The Oratory' },
}

function discoveryList(detail: EditorialDetail, key: string): string[] {
  const value = detail.discovery?.[key]
  return Array.isArray(value) ? value.map(String) : []
}
const discoveryText = (detail: EditorialDetail, key: string) => (typeof detail.discovery?.[key] === 'string' ? String(detail.discovery[key]) : null)

/** The owner's private review desk: queue, filters, bilingual texts, sources and the existing
 * verify → approve → publish transitions. The server decides who the owner is; everyone else
 * sees only an access notice and no draft data is ever fetched for them. */
export function EditorialDashboardPage() {
  const access = useEditorialAccess()
  const queue = useEditorialQueue(access.data === true)
  const [params, setParams] = useSearchParams()
  const act = useEditorialAction()
  const [confirmPublish, setConfirmPublish] = useState(false)

  const filters = {
    status: params.get('status') ?? '', tradition: params.get('tradition') ?? '', language: params.get('language') ?? '',
    theme: params.get('theme') ?? '', search: params.get('q') ?? '', batch: params.get('batch') === 'imported',
  }
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value); else next.delete(key)
    setParams(next, { replace: true })
  }
  const selected = params.get('devotion')
  const open = (slug: string | null) => setFilter('devotion', slug ?? '')
  const detail = useEditorialDetail(access.data === true ? selected : null)

  if (access.isPending) return <Loading />
  if (access.data !== true) return <>
    <PageHeader eyebrow="SCRIPTORIUM" title="Editorial Dashboard">Review and publish devotions.</PageHeader>
    <Card><Empty title="This desk is reserved"><ShieldAlert size={15} aria-hidden="true" /> The Editorial Dashboard is available only to the owner of Optima Pars.</Empty></Card>
  </>

  const devotions = (queue.data?.devotions ?? []).filter(d =>
    (!filters.status || d.status === filters.status)
    && (!filters.tradition || (d.tradition ?? '').toLowerCase().includes(filters.tradition.toLowerCase()))
    && (!filters.language || d.languages.includes(filters.language))
    && (!filters.theme || d.themes.includes(filters.theme))
    && (!filters.search || d.title.toLowerCase().includes(filters.search.toLowerCase()))
    && (!filters.batch || d.created_by === 'import:devotion-library-batch-01'))
  const summary = queue.data?.summary
  const traditions = [...new Set((queue.data?.devotions ?? []).map(d => d.tradition).filter((t): t is string => !!t))].sort()
  const themes = [...new Set((queue.data?.devotions ?? []).flatMap(d => d.themes))].sort()
  const languages = [...new Set((queue.data?.devotions ?? []).flatMap(d => d.languages))].sort()
  const index = devotions.findIndex(d => d.slug === selected)

  return <>
    <PageHeader eyebrow="SCRIPTORIUM" title="Editorial Dashboard">
      Review imported prayers, verify their sources, and publish them to The Oratory. Nothing is published without your explicit action.
    </PageHeader>
    {summary && <Card className="rule-card"><p className="muted editorial-summary" aria-label="Queue summary">
      <BookOpenCheck size={14} aria-hidden="true" /> {summary.total ?? 0} devotions · Awaiting review: {summary.proposed ?? 0} · Verified or approved: {(summary.source_verified ?? 0) + (summary.pending_approval ?? 0) + (summary.approved ?? 0)} · Published: {summary.published ?? 0}
    </p></Card>}
    {queue.isPending ? <Loading /> : queue.isError ? <Card><ErrorMessage message={queue.error.message} /></Card> : selected && detail.data ? (
      <DetailView detail={detail.data} act={act} confirmPublish={confirmPublish} setConfirmPublish={setConfirmPublish}
        onBack={() => open(null)}
        onPrevious={index > 0 ? () => open(devotions[index - 1].slug) : undefined}
        onNext={index >= 0 && index < devotions.length - 1 ? () => open(devotions[index + 1].slug) : undefined} />
    ) : <>
      <Card className="rule-card">
        <div className="editorial-filters">
          <input className="input" type="search" placeholder="Search titles…" aria-label="Search titles" value={filters.search} onChange={e => setFilter('q', e.target.value)} />
          <select className="input" aria-label="Status" value={filters.status} onChange={e => setFilter('status', e.target.value)}>
            <option value="">Any status</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select className="input" aria-label="Tradition" value={filters.tradition} onChange={e => setFilter('tradition', e.target.value)}>
            <option value="">Any tradition</option>{traditions.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="input" aria-label="Language" value={filters.language} onChange={e => setFilter('language', e.target.value)}>
            <option value="">Any language</option>{languages.map(l => <option key={l} value={l}>{LANGUAGE_NAMES[l] ?? l}</option>)}
          </select>
          <select className="input" aria-label="Theme" value={filters.theme} onChange={e => setFilter('theme', e.target.value)}>
            <option value="">Any theme</option>{themes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <label className="muted editorial-batch"><input type="checkbox" checked={filters.batch} onChange={e => setFilter('batch', e.target.checked ? 'imported' : '')} /> Imported batch only</label>
        </div>
        {devotions.length === 0 ? <Empty title="Nothing matches these filters">Loosen a filter to see more of the queue.</Empty> :
          <ul className="rule-list" aria-label="Editorial queue">
            {devotions.map(d => <li key={d.slug} className="rule-entry">
              <div className="rule-main">
                <button type="button" className="rule-title editorial-open" onClick={() => open(d.slug)}>{d.title}</button>
                <small>{STATUS_LABELS[d.status] ?? d.status} · {d.tradition ?? 'Tradition unknown'} · {d.languages.map(l => LANGUAGE_NAMES[l] ?? l).join(', ') || 'No text'} · {durationLabel(d.discovery, d.estimated_minutes)}</small>
                <small className="muted">{d.themes.join(', ') || 'No themes recorded'}{d.attribution ? ` · ${d.attribution}` : ''}{d.updated_at ? ` · Updated ${new Date(d.updated_at).toLocaleDateString()}` : ''}</small>
              </div>
            </li>)}
          </ul>}
      </Card>
    </>}
    {selected && detail.isPending && <Loading />}
    {selected && detail.isError && <Card><ErrorMessage message={detail.error.message} /><Button variant="outline" onClick={() => open(null)}>Back to queue</Button></Card>}
  </>
}

function DetailView({ detail, act, confirmPublish, setConfirmPublish, onBack, onPrevious, onNext }: {
  detail: EditorialDetail; act: ReturnType<typeof useEditorialAction>
  confirmPublish: boolean; setConfirmPublish: (v: boolean) => void
  onBack: () => void; onPrevious?: () => void; onNext?: () => void
}) {
  const next = DEVOTION_ACTIONS[detail.status]
  const run = (action: string, textId?: string) => { setConfirmPublish(false); act.mutate({ slug: detail.slug, action, textId }) }
  const english = detail.texts.filter(t => t.language === 'en')
  const original = detail.texts.filter(t => t.language !== 'en')
  return <Card className="rule-card editorial-detail">
    <div className="editorial-nav">
      <Button variant="ghost" size="sm" onClick={onBack}><ChevronLeft size={14} aria-hidden="true" /> Queue</Button>
      <span className="muted">{STATUS_LABELS[detail.status] ?? detail.status}</span>
      <span>
        <Button variant="ghost" size="sm" disabled={!onPrevious} onClick={onPrevious}><ChevronLeft size={14} aria-hidden="true" /> Previous</Button>
        <Button variant="ghost" size="sm" disabled={!onNext} onClick={onNext}>Next <ChevronRight size={14} aria-hidden="true" /></Button>
      </span>
    </div>
    <h2 className="rule-settings-title">{detail.title}</h2>
    <p className="muted">{detail.tradition ?? 'Tradition unknown'} · {durationLabel(detail.discovery, detail.estimated_minutes)}{discoveryText(detail, 'attribution') ? ` · ${discoveryText(detail, 'attribution')}` : ''}{discoveryText(detail, 'attribution_confidence') ? ` (attribution confidence: ${discoveryText(detail, 'attribution_confidence')})` : ''}</p>

    <div className={original.length ? 'editorial-texts two' : 'editorial-texts'}>
      {original.map(text => <section key={text.id} aria-label={`${LANGUAGE_NAMES[text.language] ?? text.language} text`}>
        <h3>{LANGUAGE_NAMES[text.language] ?? text.language} <small className="muted">({STATUS_LABELS[text.status] ?? text.status})</small></h3>
        <pre className="editorial-prayer" lang={text.language}>{text.body}</pre>
        <TextActions text={text} run={run} pending={act.isPending} />
      </section>)}
      {english.map(text => <section key={text.id} aria-label="English text">
        <h3>English {text.is_translation && text.translator ? <small className="muted">(tr. {text.translator})</small> : null} <small className="muted">({STATUS_LABELS[text.status] ?? text.status})</small></h3>
        <pre className="editorial-prayer" lang="en">{text.body}</pre>
        <TextActions text={text} run={run} pending={act.isPending} />
      </section>)}
    </div>

    <h3>History</h3>
    <p className="editorial-prose">{detail.overview}</p>
    {detail.background && <><h3>Textual notes</h3><p className="editorial-prose">{detail.background}</p></>}
    <Facts detail={detail} />
    <h3>Sources</h3>
    {detail.references.length === 0 ? <p className="muted">No sources recorded.</p> :
      <ul className="editorial-sources">{detail.references.map((ref, i) => <li key={i}>{ref.url ? <a href={ref.url} target="_blank" rel="noreferrer">{ref.label}</a> : ref.label}</li>)}</ul>}
    {english.map(t => t.license_notes && <p key={t.id} className="muted">Rights: {t.license_notes} ({t.license_status.replaceAll('_', ' ')})</p>)}

    <div className="editorial-actions">
      {next && (next.action !== 'publish' || confirmPublish
        ? <Button disabled={act.isPending} onClick={() => run(next.action)}>{next.action === 'publish' ? 'Yes, publish this devotion' : next.label}</Button>
        : <Button disabled={act.isPending} onClick={() => setConfirmPublish(true)}>{next.label}…</Button>)}
      {next?.action === 'publish' && confirmPublish && <Button variant="outline" onClick={() => setConfirmPublish(false)}>Not yet</Button>}
      {detail.status !== 'proposed' && <Button variant="outline" disabled={act.isPending} onClick={() => run('return')}>Return for further work</Button>}
    </div>
    {act.isError && <ErrorMessage message={act.error instanceof Error ? act.error.message : 'The action failed.'} />}
    {act.isSuccess && <p className="muted">Saved. {detail.status === 'published' ? 'This devotion is now visible in The Oratory.' : ''}</p>}
    <h3>Editorial history</h3>
    <ul className="editorial-sources">{detail.events.map((e, i) => <li key={i} className="muted">{new Date(e.at).toLocaleString()} — {e.action}{e.to_status ? ` → ${e.to_status}` : ''} ({e.actor})</li>)}</ul>
  </Card>
}

function TextActions({ text, run, pending }: { text: { id: string; status: string }; run: (action: string, textId?: string) => void; pending: boolean }) {
  if (text.status === 'proposed') return <Button variant="outline" size="sm" disabled={pending} onClick={() => run('verify-source', text.id)}>Mark source verified</Button>
  if (text.status === 'source_verified') return <Button variant="outline" size="sm" disabled={pending} onClick={() => run('approve', text.id)}>Approve text</Button>
  return null
}

function Facts({ detail }: { detail: EditorialDetail }) {
  const rows: [string, string | null][] = [
    ['Theological themes', discoveryList(detail, 'theological_themes').join(', ') || null],
    ['Devotional focus', discoveryList(detail, 'devotional_focus').join(', ') || null],
    ['Spiritual purpose', discoveryList(detail, 'spiritual_purpose').join(', ') || null],
    ['Associated churches', discoveryList(detail, 'associated_churches').join(', ') || null],
    ['Regions', discoveryList(detail, 'regional_associations').join(', ') || null],
    ['Prayer form', discoveryText(detail, 'prayer_form')],
    ['Liturgical season', discoveryText(detail, 'liturgical_season')],
    ['Occasions', discoveryList(detail, 'occasions').join(', ') || null],
    ['Suggested context', discoveryText(detail, 'suggested_context')],
    ['Reuse status', discoveryText(detail, 'reuse_status')?.replaceAll('_', ' ') ?? null],
  ]
  const known = rows.filter(([, value]) => value)
  if (known.length === 0) return <p className="muted">No discovery metadata recorded for this devotion.</p>
  return <dl className="editorial-facts">{known.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}
