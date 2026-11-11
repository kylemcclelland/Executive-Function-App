import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Church } from 'lucide-react'
import { Card } from '../ui'
import { longDate, today } from '../../lib/divineOffice'
import { ROMCAL_SOURCE, currentRomanDay, sameSaint } from '../../lib/romcalCalendar'
import { api } from '../../services/api'
import type { CalendarDay } from '../../types/liturgicalCalendar'

export type CalendarProvider = 'traditional' | 'current'
export const CALENDAR_PROVIDER_KEY = 'optima.calendar-provider'
const PROVIDERS: { key: CalendarProvider; label: string }[] = [{ key: 'traditional', label: 'Traditional (1960)' }, { key: 'current', label: 'Current Roman' }]

/** The saved choice; the traditional calendar unless the reader chose the current one. */
function savedProvider(): CalendarProvider {
  try { return window.localStorage.getItem(CALENDAR_PROVIDER_KEY) === 'current' ? 'current' : 'traditional' } catch { return 'traditional' }
}

/**
 * The principal celebration of today in the reader's chosen calendar: the traditional 1960 Roman calendar (Divinum Officium) or the current Roman
 * calendar (Romcal, United States propers). The date is the reader's local date, never UTC. Nothing is shown in place of missing information.
 */
export function LiturgicalCalendarCard() {
  const date = today()
  const [provider, setProviderState] = useState<CalendarProvider>(savedProvider)
  const setProvider = (next: CalendarProvider) => {
    setProviderState(next)
    try { window.localStorage.setItem(CALENDAR_PROVIDER_KEY, next) } catch { /* the choice just is not remembered */ }
  }
  const current = provider === 'current'
  const traditional = useQuery({
    queryKey: ['liturgical-calendar', date],
    queryFn: () => api<CalendarDay>(`/liturgical-calendar/${date}?edition=roman_1960`),
    retry: false,
    staleTime: 60 * 60 * 1000,
  })
  const modern = useQuery({ queryKey: ['current-roman-calendar', date], queryFn: () => currentRomanDay(date), enabled: current, retry: false, staleTime: 60 * 60 * 1000 })
  const heading = current ? 'Current Roman Calendar' : 'Traditional Liturgical Calendar'
  return <Card className="calendar-card" aria-labelledby="calendar-card-title">
    <div className="section-heading"><div className="section-title"><Church size={17} aria-hidden="true" /><p className="eyebrow" id="calendar-card-title">{heading}</p></div></div>
    <div className="calendar-switch" role="group" aria-label="Liturgical calendar">
      {PROVIDERS.map(item => <button key={item.key} type="button" className="calendar-switch-option" aria-pressed={provider === item.key} onClick={() => setProvider(item.key)}>{item.label}</button>)}
    </div>
    <p className="calendar-date">{longDate(date)}</p>
    {current ? <CurrentDay query={modern} traditional={traditional.data} /> : <TraditionalDay query={traditional} date={date} />}
  </Card>
}

function TraditionalDay({ query, date }: { query: { isPending: boolean; isError: boolean; data: CalendarDay | undefined }; date: string }) {
  const day = query.data
  return <>
    {query.isPending && <p className="muted" role="status">Looking up the day…</p>}
    {query.isError && <p className="muted" role="status">The traditional calendar is unavailable right now. Your day is unaffected.</p>}
    {day && <>
      <h2 className="calendar-celebration" lang={day.celebration_source === 'latin_untranslated' ? 'la' : 'en'} title={day.english_correction ?? undefined}>{day.celebration}</h2>
      {day.rank_label && <p className="calendar-rank">{day.rank_label}</p>}
      {day.celebration_source !== 'latin_untranslated' && day.celebration_latin && <p className="calendar-latin" lang="la">{day.celebration_latin}</p>}
      {day.designation && <p className="calendar-designation">{day.designation}</p>}
      {day.season && <p className="calendar-season">{day.season}</p>}
      {day.description && <Description text={day.description.text} source={day.description.source} />}
      {day.commemorations.length > 0 && <p className="calendar-commemorations"><span>Commemorated: </span>{day.commemorations.map(item => item.english ?? item.latin).join('; ')}</p>}
      <Link className="calendar-link" to={`/divine-office?date=${date}`}>Read Today’s Divine Office <ArrowRight size={14} aria-hidden="true" /></Link>
    </>}
  </>
}

/** The current calendar names no Divine Office link: the Office offered here is the traditional Breviary, which is not the modern Liturgy of the Hours. */
function CurrentDay({ query, traditional }: { query: { isPending: boolean; isError: boolean; data: Awaited<ReturnType<typeof currentRomanDay>> | undefined }; traditional: CalendarDay | undefined }) {
  const day = query.data
  return <>
    {query.isPending && <p className="muted" role="status">Looking up the day…</p>}
    {query.isError && <p className="muted" role="status">The current Roman calendar is unavailable right now. Your day is unaffected.</p>}
    {query.data === null && <p className="muted" role="status">The current Roman calendar has no entry for this date.</p>}
    {day && <>
      <h2 className="calendar-celebration" lang="en">{day.name}</h2>
      <p className="calendar-rank">{day.rankLabel}</p>
      <p className="calendar-season">{[day.season, day.color && `${day.color} vestments`].filter(Boolean).join(' · ')}</p>
      {sameSaint(day, traditional) && traditional?.description && <Description text={traditional.description.text} source={traditional.description.source} traditional />}
      {day.optionalMemorials.length > 0 && <p className="calendar-commemorations"><span>Optional memorials: </span>{day.optionalMemorials.map(item => item.name).join('; ')}</p>}
      <p className="calendar-source" title={`${ROMCAL_SOURCE.calendar}; ${ROMCAL_SOURCE.url}`}>Calendar: {ROMCAL_SOURCE.name} {ROMCAL_SOURCE.version}, United States{day.calendarId === 'united_states' ? ' (US proper)' : ''}</p>
    </>}
  </>
}

function Description({ text, source, traditional = false }: { text: string; source: { name: string; reference: string }; traditional?: boolean }) {
  return <>
    <p className="calendar-description">{text}</p>
    <p className="calendar-source" title={source.reference}>{traditional ? 'Traditional Breviary lesson. ' : ''}Source: {source.name}</p>
  </>
}
