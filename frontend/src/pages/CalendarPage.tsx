import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Link2, RefreshCw, Unplug } from 'lucide-react'
import { Button, Card, Dialog } from '../components/ui'
import { ErrorMessage, Loading, PageHeader } from '../components/common'
import { EventRow } from '../components/calendar/EventRow'
import { PrayerOccurrenceRow } from '../components/ruleOfLife/PrayerOccurrenceRow'
import { api, ApiError } from '../services/api'
import { useAction } from '../hooks/useAction'
import { CALENDAR_API, dayHeading, groupByDay, useCalendarStatus } from '../lib/calendar'
import { useRuleOccurrences } from '../lib/ruleOfLife'
import type { RuleOccurrence } from '../types/ruleOfLife'
import type { CalendarEvent, CalendarEventsPage } from '../types'

const RETURN_MESSAGES: Record<string, { ok: boolean; text: string }> = {
  connected: { ok: true, text: 'Google Calendar is connected.' },
  access_denied: { ok: true, text: 'No problem. Nothing was connected, and Optima Pars works just as well without it.' },
  missing_scope: { ok: false, text: 'Calendar access was not granted. To connect, tick the calendar permission on Google’s consent screen.' },
  no_refresh_token: { ok: false, text: 'Google did not allow Optima Pars to stay connected. Please try connecting again.' },
  invalid_state: { ok: false, text: 'That connection attempt expired or was already used. Please start again.' },
  failed: { ok: false, text: 'Google Calendar could not be connected. Please try again.' },
}

function updated(value: string | null) {
  return value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'not yet'
}

export function CalendarPage() {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [returned] = useState(() => params.get('google'))
  const status = useCalendarStatus()
  const timezone = useQuery({ queryKey: ['user'], queryFn: () => api<{ timezone: string }>('/user'), retry: false }).data?.timezone
  const connect = useAction()
  const disconnect = useAction()
  const [confirming, setConfirming] = useState(false)
  const [rangeStart] = useState(() => new Date().toISOString())

  useEffect(() => {
    // The outcome was read on arrival (Google's redirect is a full page load); now tidy the URL.
    if (!params.has('google')) return
    void client.invalidateQueries({ queryKey: ['calendar-status'] })
    setParams({}, { replace: true })
  }, [params, setParams, client])

  const active = status.data?.status === 'active'
  const events = useInfiniteQuery({
    queryKey: ['calendar-events', rangeStart],
    queryFn: ({ pageParam }) => api<CalendarEventsPage>(`${CALENDAR_API}/events?time_min=${encodeURIComponent(rangeStart)}${pageParam ? `&page_token=${encodeURIComponent(pageParam)}` : ''}`),
    initialPageParam: null as string | null,
    getNextPageParam: last => last.next_page_token,
    enabled: active, retry: false,
  })
  const stale = events.error instanceof ApiError && events.error.status === 409
  useEffect(() => { if (stale) void client.invalidateQueries({ queryKey: ['calendar-status'] }) }, [stale, client])

  function startConnecting() {
    void connect.run(async () => {
      const { authorization_url } = await api<{ authorization_url: string }>(`${CALENDAR_API}/connect`, 'POST')
      if (!authorization_url.startsWith('https://accounts.google.com/')) throw new Error('Unexpected response. Please try again.')
      window.location.assign(authorization_url)
    })
  }

  const message = returned ? RETURN_MESSAGES[returned] : undefined
  const groups = groupByDay(events.data?.pages.flatMap(page => page.events) ?? [], timezone)
  // The Rule of Life's scheduled prayers share the same days as appointments: one list, ordered by time within each day.
  const [today] = useState(() => new Date())
  const prayers = useRuleOccurrences(today, 30).data ?? []
  const days = mergeDays(groups, prayers, timezone)
  return <>
    <PageHeader eyebrow="CALENDAR" title="Calendar">The days ahead, read from your Google Calendar. Optima Pars never changes it.</PageHeader>
    {message && <p className={message.ok ? 'success-message calendar-notice' : 'error-message'} role={message.ok ? 'status' : 'alert'}>{message.text}</p>}
    {status.isPending ? <Loading /> : status.isError ? <Card><ErrorMessage message={status.error.message} /><Button variant="outline" onClick={() => void status.refetch()}>Try again</Button></Card> :
      !status.data.configured ? <Card className="calendar-card"><span className="future-icon"><CalendarDays size={30} strokeWidth={1.4} /></span><h2>Google Calendar isn’t set up here</h2><p className="muted">This Optima Pars server has no Google credentials yet, so there is nothing to connect. Everything else works as usual.</p></Card> :
      status.data.status === 'not_connected' ? <Card className="calendar-card">
        <span className="future-icon"><CalendarDays size={30} strokeWidth={1.4} /></span>
        <h2>Connect Google Calendar</h2>
        <p className="muted">See your upcoming events here and on Today. Optima Pars asks for read-only access to your calendar and nothing else, and you can disconnect at any time. It is entirely optional.</p>
        <Button onClick={startConnecting} disabled={connect.pending}><Link2 size={16} /> {connect.pending ? 'Opening Google…' : 'Connect Google Calendar'}</Button>
        <ErrorMessage message={connect.error} />
      </Card> : <>
        <Card className="calendar-connection">
          <div><p className="eyebrow">{active ? 'CONNECTED' : 'ACTION NEEDED'}</p>
            <h2>{status.data.account_email ?? 'Google Calendar'}</h2>
            <p className="muted">{active ? `Last updated ${updated(status.data.last_successful_sync_at)}.` : 'Google no longer allows Optima Pars to read this calendar. Reconnect to continue.'}</p></div>
          <div className="calendar-actions">
            {!active && <Button onClick={startConnecting} disabled={connect.pending}><RefreshCw size={15} /> {connect.pending ? 'Opening Google…' : 'Reconnect'}</Button>}
            <Button variant="outline" onClick={() => setConfirming(true)}><Unplug size={15} /> Disconnect</Button>
          </div>
          <ErrorMessage message={connect.error} />
        </Card>
        {active && <Card className="calendar-events">
          <div className="section-title"><CalendarDays size={17} /><h2>Upcoming</h2></div>
          {events.isPending ? <Loading /> : events.isError && !stale ? <><ErrorMessage message={events.error.message} /><Button variant="outline" onClick={() => void events.refetch()}>Try again</Button></> :
            days.length === 0 ? <p className="muted">Nothing on your calendar in the next 30 days.</p> : <>
              {days.map(group => <DaySection key={group.day} group={group} timezone={timezone} />)}
              {events.hasNextPage && <Button variant="outline" onClick={() => void events.fetchNextPage()} disabled={events.isFetchingNextPage}>{events.isFetchingNextPage ? 'Loading…' : 'Show more'}</Button>}
              {events.isFetchNextPageError && <ErrorMessage message={events.error?.message ?? 'Could not load more events.'} />}
            </>}
        </Card>}
      </>}
    {!active && !status.isPending && days.length > 0 && <Card className="calendar-events">
      <div className="section-title"><CalendarDays size={17} /><h2>Rule of Life</h2></div>
      {days.map(group => <DaySection key={group.day} group={group} timezone={timezone} />)}
    </Card>}
    {confirming && <Dialog open onOpenChange={open => { if (!open && !disconnect.pending) setConfirming(false) }} title="Disconnect Google Calendar?" description="Optima Pars will stop reading your calendar and forget the connection. Your Google account and events are not changed. You can reconnect whenever you like.">
      <ErrorMessage message={disconnect.error} />
      <div className="dialog-actions"><Button variant="outline" onClick={() => setConfirming(false)} disabled={disconnect.pending}>Keep connected</Button><Button variant="destructive" disabled={disconnect.pending} onClick={() => void disconnect.run(() => api(`${CALENDAR_API}/disconnect`, 'DELETE'), () => setConfirming(false))}>{disconnect.pending ? 'Disconnecting…' : 'Disconnect'}</Button></div>
    </Dialog>}
  </>
}

type Day = { day: string; events: CalendarEvent[]; prayers: RuleOccurrence[] }

/** Appointments and Rule of Life prayers by day, soonest day first. */
function mergeDays(groups: { day: string; events: CalendarEvent[] }[], prayers: RuleOccurrence[], timeZone?: string): Day[] {
  const days = new Map<string, Day>()
  const at = (day: string) => days.get(day) ?? days.set(day, { day, events: [], prayers: [] }).get(day)!
  for (const group of groups) at(group.day).events.push(...group.events)
  for (const prayer of prayers) at(prayer.date).prayers.push(prayer)
  void timeZone
  return [...days.values()].sort((a, b) => a.day.localeCompare(b.day))
}

function DaySection({ group, timezone }: { group: Day; timezone?: string }) {
  // All-day events first, then everything else by its start instant.
  const items = [
    ...group.events.map(event => ({ at: event.all_day || !event.start ? -Infinity : Date.parse(event.start), node: <EventRow key={event.id + (event.start ?? event.start_date)} event={event} timeZone={timezone} /> })),
    ...group.prayers.map(prayer => ({ at: Date.parse(prayer.start), node: <PrayerOccurrenceRow key={`${prayer.entry_id}-${prayer.date}`} occurrence={prayer} /> })),
  ].sort((a, b) => a.at - b.at)
  return <section className="event-day"><h3>{dayHeading(group.day, timezone)}</h3><ul className="event-list">{items.map(item => item.node)}</ul></section>
}
