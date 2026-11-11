import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Church } from 'lucide-react'
import { Card } from '../ui'
import { longDate, today } from '../../lib/divineOffice'
import { api } from '../../services/api'
import type { CalendarDay } from '../../types/liturgicalCalendar'

/**
 * The principal celebration of today in the traditional (1960 Roman) calendar, with its rank and, where the engine's own Matins lesson
 * supports one, a short description. The date is the reader's local date, never UTC. Nothing is shown in place of missing information.
 */
export function LiturgicalCalendarCard() {
  const date = today()
  const query = useQuery({
    queryKey: ['liturgical-calendar', date],
    queryFn: () => api<CalendarDay>(`/liturgical-calendar/${date}?edition=roman_1960`),
    retry: false,
    staleTime: 60 * 60 * 1000,
  })
  const day = query.data
  return <Card className="calendar-card" aria-labelledby="calendar-card-title">
    <div className="section-heading"><div className="section-title"><Church size={17} aria-hidden="true" /><p className="eyebrow" id="calendar-card-title">Traditional Liturgical Calendar</p></div></div>
    <p className="calendar-date">{longDate(date)}</p>
    {query.isPending && <p className="muted" role="status">Looking up the day…</p>}
    {query.isError && <p className="muted" role="status">The traditional calendar is unavailable right now. Your day is unaffected.</p>}
    {day && <>
      <h2 className="calendar-celebration" lang={day.celebration_source === 'latin_untranslated' ? 'la' : 'en'} title={day.english_correction ?? undefined}>{day.celebration}</h2>
      {day.rank_label && <p className="calendar-rank">{day.rank_label}</p>}
      {day.celebration_source !== 'latin_untranslated' && day.celebration_latin && <p className="calendar-latin" lang="la">{day.celebration_latin}</p>}
      {day.designation && <p className="calendar-designation">{day.designation}</p>}
      {day.season && <p className="calendar-season">{day.season}</p>}
      {day.description && <>
        <p className="calendar-description">{day.description.text}</p>
        <p className="calendar-source" title={day.description.source.reference}>Source: {day.description.source.name}</p>
      </>}
      {day.commemorations.length > 0 && <p className="calendar-commemorations"><span>Commemorated: </span>{day.commemorations.map(item => item.english ?? item.latin).join('; ')}</p>}
      <Link className="calendar-link" to={`/divine-office?date=${date}`}>Read Today’s Divine Office <ArrowRight size={14} aria-hidden="true" /></Link>
    </>}
  </Card>
}
