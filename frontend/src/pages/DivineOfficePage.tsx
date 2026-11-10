import { createContext, useContext, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Bookmark, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '../components/ui'
import { Empty, Loading } from '../components/common'
import { isResponseLine } from '../lib/devotions'
import { DEFAULT_HOUR, OFFICE_HOURS, OFFICE_VIEW_KEY, isOfficeView, isValidIsoDate, longDate, shiftDate, today, unitTitle } from '../lib/divineOffice'
import { ApiError, api } from '../services/api'
import type { Office, OfficeHour, OfficeLine, OfficeMark, OfficeRow, OfficeSection, OfficeUnit, OfficeView, SavedOfficeBrief } from '../types/divineOffice'
import '../components/devotions/divine-office.css'

function storedView(): OfficeView {
  try {
    const saved = window.localStorage.getItem(OFFICE_VIEW_KEY)
    return isOfficeView(saved) ? saved : 'english'
  } catch { return 'english' }
}

/** What the reader needs to save and unsave prayers without leaving the Office. ``ready`` is false when saving is not available. */
interface SaveControls { ready: boolean; saved: Map<string, SavedOfficeBrief>; pending: string | null; view: OfficeView; toggle: (unit: OfficeUnit) => void }
const SaveContext = createContext<SaveControls | null>(null)

function SaveButton({ unit }: { unit: OfficeUnit }) {
  const controls = useContext(SaveContext)
  if (!controls?.ready) return null
  const isSaved = controls.saved.has(unit.id)
  const title = unitTitle(unit, controls.view)
  const label = `${isSaved ? 'Remove from Saved Prayers' : 'Save to Saved Prayers'}: ${title}${unit.date_specific ? ' (this day)' : ''}`
  return <button type="button" className={`office-save${isSaved ? ' is-saved' : ''}`} aria-pressed={isSaved} aria-label={label} title={label} disabled={controls.pending === unit.id} onClick={() => controls.toggle(unit)}>
    <Bookmark size={16} aria-hidden="true" fill={isSaved ? 'currentColor' : 'none'} />
  </button>
}

/** The id under which a mark (nocturn, Te Deum, commemoration) can be linked to from the contents. */
const markId = (section: OfficeSection, row: number, line: number) => `office-${section.id}-${row}-${line}`

function OfficeLineView({ line, language, mark, anchor }: { line: OfficeLine; language: 'la' | 'en'; mark?: OfficeMark; anchor?: string }) {
  const response = line.kind === 'versicle' || line.kind === 'response' || isResponseLine(line.label ?? '')
  if (mark?.kind === 'nocturn') return <h3 className="office-nocturn" id={anchor} lang={language}>{line.text}</h3>
  return <p id={anchor} className={`office-line is-${line.kind}${response ? ' is-response' : ''}${mark ? ` is-mark is-${mark.kind}` : ''}`} lang={language}>
    {line.label && <span className="office-label">{line.label} </span>}{line.text}
  </p>
}

function Column({ lines, language, row, section, rowIndex, withAnchors }: { lines: OfficeLine[]; language: 'la' | 'en'; row: OfficeRow; section: OfficeSection; rowIndex: number; withAnchors: boolean }) {
  return <div className="office-column" lang={language}>{lines.map((line, index) => {
    const mark = row.marks.find(item => item.line === index)
    const unit = withAnchors ? (row.units ?? []).find(item => item.start === index) : undefined      // one Save control per unit: in the first column only
    const view = <OfficeLineView key={index} line={line} language={language} mark={mark} anchor={mark && withAnchors ? markId(section, rowIndex, index) : undefined} />
    return unit ? <div className="office-unit-start" key={index}>{view}<SaveButton unit={unit} /></div> : view
  })}</div>
}

function sectionHeading(section: OfficeSection, view: OfficeView): string | null {
  if (view === 'both') return [section.heading_latin, section.heading_english].filter(Boolean).join(' · ') || null
  return (view === 'latin' ? section.heading_latin : section.heading_english) || null
}

function markLabel(mark: OfficeMark, view: OfficeView): string {
  if (view === 'latin') return mark.latin
  if (view === 'english') return mark.english ?? mark.latin
  return mark.english && mark.english !== mark.latin ? `${mark.latin} · ${mark.english}` : mark.latin
}

/** A table of contents for the hour: every part, with the nocturns, the Te Deum and any commemorations inside them. */
function Contents({ office, view }: { office: Office; view: OfficeView }) {
  return <nav className="office-toc" aria-label="Contents">
    <details open={office.hour === 'matins'}>
      <summary>Contents</summary>
      <ol>{office.sections.map((section, sectionIndex) => {
        const marks = section.rows.flatMap((row, rowIndex) => row.marks.map(mark => ({ mark, rowIndex })))
        return <li key={section.id}>
          <a href={`#office-${section.id}`}>{sectionHeading(section, view) ?? `Part ${sectionIndex + 1}`}</a>
          {marks.length > 0 && <ul>{marks.map(({ mark, rowIndex }) => <li key={`${rowIndex}-${mark.line}`}><a href={`#${markId(section, rowIndex, mark.line)}`}>{markLabel(mark, view)}</a></li>)}</ul>}
        </li>
      })}</ol>
    </details>
  </nav>
}

function SectionView({ section, view }: { section: OfficeSection; view: OfficeView }) {
  const headings = sectionHeading(section, view)
  const note = view === 'both' ? [section.note_latin, section.note_english].filter(Boolean).join(' · ') : (view === 'latin' ? section.note_latin : section.note_english)
  return <section className="office-section" id={`office-${section.id}`} aria-labelledby={headings ? `office-${section.id}-title` : undefined}>
    {headings && <h2 id={`office-${section.id}-title`}>{headings}</h2>}
    {note && <p className="office-note">{note}</p>}
    {section.rows.map((row, index) => view === 'both'
      ? <div className={`office-pair${row.aligned ? '' : ' is-unaligned'}`} key={index}>
          <Column lines={row.latin} language="la" row={row} section={section} rowIndex={index} withAnchors />
          <Column lines={row.english} language="en" row={row} section={section} rowIndex={index} withAnchors={false} />
        </div>
      : <Column key={index} lines={view === 'latin' ? row.latin : row.english} language={view === 'latin' ? 'la' : 'en'} row={row} section={section} rowIndex={index} withAnchors />)}
  </section>
}

function HourSelector({ hours, current, onChoose }: { hours: OfficeHour[]; current: string; onChoose: (hour: string) => void }) {
  return <div className="office-hours" role="group" aria-label="Hour">
    {hours.map(hour => hour.available
      ? <button key={hour.slug} type="button" className="office-hour" aria-pressed={hour.slug === current} onClick={() => onChoose(hour.slug)}><span>{hour.name}</span><small>{hour.latin}</small></button>
      : <button key={hour.slug} type="button" className="office-hour is-forthcoming" disabled aria-label={`${hour.name} (forthcoming)`}><span>{hour.name}</span><small>Forthcoming</small></button>)}
  </div>
}

/** The Divine Office within The Oratory: Roman Breviary, Rubrics of 1960. Compline is available; the other hours are forthcoming. */
export function DivineOfficePage() {
  const [params, setParams] = useSearchParams()
  const dateParam = params.get('date')
  const date = isValidIsoDate(dateParam) ? dateParam : today()
  const hourParam = params.get('hour')
  const hour = OFFICE_HOURS.some(item => item.slug === hourParam) ? hourParam! : DEFAULT_HOUR
  const [view, setViewState] = useState<OfficeView>(storedView)
  const setView = (next: OfficeView) => { setViewState(next); try { window.localStorage.setItem(OFFICE_VIEW_KEY, next) } catch { /* the choice just is not remembered */ } }
  const go = (next: { date?: string; hour?: string }) => setParams(current => {
    const updated = new URLSearchParams(current)
    updated.set('date', next.date ?? date)
    updated.set('hour', next.hour ?? hour)
    return updated
  })
  const available = OFFICE_HOURS.find(item => item.slug === hour)?.available ?? false
  const query = useQuery({ queryKey: ['divine-office', date, hour], queryFn: () => api<Office>(`/divine-office/${date}/${hour}`), enabled: available, retry: false })
  const office = query.data
  const client = useQueryClient()
  const savedQuery = useQuery({ queryKey: ['office-saved'], queryFn: () => api<SavedOfficeBrief[]>('/divine-office/saved'), retry: false })
  const savedByKey = new Map((Array.isArray(savedQuery.data) ? savedQuery.data : []).map(item => [item.unit_key, item]))
  const toggle = useMutation({
    mutationFn: (unit: OfficeUnit) => {
      const existing = savedByKey.get(unit.id)
      return existing ? api(`/divine-office/saved/${existing.id}`, 'DELETE') : api('/divine-office/saved', 'POST', { date, hour, unit_id: unit.id })
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ['office-saved'] }),
  })
  const controls: SaveControls = { ready: savedQuery.isSuccess && Array.isArray(savedQuery.data), saved: savedByKey, pending: toggle.isPending ? (toggle.variables?.id ?? null) : null, view, toggle: unit => toggle.mutate(unit) }

  return <article className="office" aria-labelledby="office-title">
    <header className="office-header">
      <Link to="/devotions" className="devotion-back"><ArrowLeft size={16} aria-hidden="true" /> The Oratory</Link>
      <h1 id="office-title">The Divine Office</h1>
      <p className="office-subtitle">Roman Breviary · Rubrics of 1960 · Universal Roman calendar</p>
      <div className="office-date" role="group" aria-label="Date navigation">
        <Button variant="outline" size="icon" aria-label="Previous day" onClick={() => go({ date: shiftDate(date, -1) })}><ChevronLeft size={18} /></Button>
        <label className="office-date-field">
          <input type="date" aria-label="Office date" value={date} onChange={event => { if (isValidIsoDate(event.target.value)) go({ date: event.target.value }) }} />
        </label>
        <Button variant="outline" size="icon" aria-label="Next day" onClick={() => go({ date: shiftDate(date, 1) })}><ChevronRight size={18} /></Button>
        <Button variant="outline" size="sm" disabled={date === today()} onClick={() => go({ date: today() })}>Today</Button>
      </div>
      <HourSelector hours={OFFICE_HOURS} current={hour} onChoose={next => go({ hour: next })} />
      <div className="office-view" role="group" aria-label="Language">
        {([['english', 'English'], ['latin', 'Latin'], ['both', 'Side by side']] as const).map(([key, label]) => <Button key={key} size="sm" variant={view === key ? 'secondary' : 'ghost'} aria-pressed={view === key} onClick={() => setView(key)}>{label}</Button>)}
      </div>
    </header>

    {!available ? <Empty title={`${OFFICE_HOURS.find(item => item.slug === hour)?.name} is forthcoming`}>Only Compline is available so far. <button type="button" className="office-link" onClick={() => go({ hour: DEFAULT_HOUR })}>Open Compline</button>.</Empty>
      : query.isPending ? <Loading />
      : query.isError ? <>
          <div className="office-unavailable" role="alert">
            <p><strong>{query.error instanceof ApiError && query.error.status === 503 ? 'The Divine Office is unavailable.' : 'The Office could not be loaded.'}</strong></p>
            <p>{query.error.message}</p>
            <p className="muted">Nothing is shown in its place: the Office is only ever the upstream engine’s own text.</p>
          </div>
          <Button variant="outline" onClick={() => void query.refetch()}>Try again</Button>
        </>
      : office && <>
          <section className="office-day" aria-label="Liturgical day">
            <p className="office-date-long">{longDate(office.date)}</p>
            {office.liturgical_day && <h2 className="office-feast">{office.liturgical_day}</h2>}
            <p className="office-meta">{[office.season, office.rank].filter(Boolean).join(' · ')}</p>
            <p className="office-hour-title">{office.hour_name} <span lang="la">({office.hour_latin})</span></p>
          </section>
          <Contents office={office} view={view} />
          {savedQuery.isError && <p className="office-note" role="status">Saving prayers is not available on this server.</p>}
          {toggle.isError && <p className="office-note" role="alert">{toggle.error.message}</p>}
          <SaveContext.Provider value={controls}>
            {office.sections.map(section => <SectionView key={section.id} section={section} view={view} />)}
          </SaveContext.Provider>
          <footer className="office-source">
            <p><strong>Source.</strong> <a href={office.source.url} target="_blank" rel="noopener noreferrer">{office.source.name}</a>, version “{office.source.version}”{office.source.commit ? `, commit ${office.source.commit.slice(0, 10)}` : ''}. Software licence: {office.source.code_license}.</p>
            <p className="muted">{office.source.texts}</p>
          </footer>
        </>}
  </article>
}
