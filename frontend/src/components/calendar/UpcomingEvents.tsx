import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CalendarDays } from 'lucide-react'
import { Button, Card } from '../ui'
import { Loading } from '../common'
import { EventRow } from './EventRow'
import { api } from '../../services/api'
import { CALENDAR_API, dayHeading, eventDay, useCalendarStatus } from '../../lib/calendar'
import type { CalendarEventsPage } from '../../types'

const SHOWN = 4

/** The next few events on Today. Entirely optional: renders nothing unless Google Calendar is offered. */
export function UpcomingEvents({ timeZone }: { timeZone?: string }) {
  const status = useCalendarStatus()
  const active = status.data?.status === 'active'
  const events = useQuery({
    queryKey: ['calendar-upcoming'],
    queryFn: () => api<CalendarEventsPage>(`${CALENDAR_API}/events?page_size=${SHOWN + 2}&time_min=${encodeURIComponent(new Date().toISOString())}`),
    enabled: active, retry: false, refetchInterval: 5 * 60_000,
  })
  if (!status.data?.configured) return null
  if (status.data.status !== 'active') {
    const reconnect = status.data.status === 'needs_reauth'
    return <Card className="upcoming-card">
      <div className="section-title"><CalendarDays size={17} /><h2>Coming up</h2></div>
      <p className="muted">{reconnect ? 'Google Calendar needs to be reconnected before it can show your events.' : 'Connect Google Calendar to see what is ahead, alongside your priorities. It is optional and read-only.'}</p>
      <Button asChild variant="outline" size="sm"><Link to="/calendar">{reconnect ? 'Reconnect Google Calendar' : 'Connect Google Calendar'} <ArrowRight size={14} /></Link></Button>
    </Card>
  }
  const upcoming = events.data?.events.slice(0, SHOWN) ?? []
  return <Card className="upcoming-card">
    <div className="section-title"><CalendarDays size={17} /><h2>Coming up</h2></div>
    {events.isPending ? <Loading /> : events.isError ? <p className="muted">Your calendar could not be loaded just now.</p> : upcoming.length === 0 ? <p className="muted">Nothing scheduled soon.</p> :
      <ul className="event-list">{upcoming.map(event => <EventRow key={event.id + (event.start ?? event.start_date)} event={event} timeZone={timeZone} prefix={dayHeading(eventDay(event, timeZone), timeZone)} />)}</ul>}
    <div className="previous-footer"><Link to="/calendar">Open calendar <ArrowRight size={13} /></Link></div>
  </Card>
}
