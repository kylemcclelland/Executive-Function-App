import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import { formatDate } from './utils'
import type { CalendarEvent, CalendarStatus } from '../types'

export const CALENDAR_API = '/integrations/google-calendar'

/** Connection state only: it never contains calendar data, and failing to load it is never fatal. */
export function useCalendarStatus() {
  return useQuery({ queryKey: ['calendar-status'], queryFn: () => api<CalendarStatus>(`${CALENDAR_API}/status`), retry: false, staleTime: 30_000 })
}

/** YYYY-MM-DD for an instant as seen in the given IANA zone (falls back to the browser's). */
export function localDay(instant: Date, timeZone?: string) {
  try { return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(instant) }
  catch { return new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(instant) }
}

/** The calendar day an event belongs to, in the user's timezone. All-day events keep their own date. */
export function eventDay(event: CalendarEvent, timeZone?: string) {
  if (event.all_day) return event.start_date ?? ''
  return event.start ? localDay(new Date(event.start), timeZone) : ''
}

function clock(value: string, timeZone?: string, withDate = false) {
  const options: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit', ...(withDate ? { month: 'short', day: 'numeric' } : {}) }
  try { return new Intl.DateTimeFormat(undefined, { ...options, timeZone }).format(new Date(value)) }
  catch { return new Intl.DateTimeFormat(undefined, options).format(new Date(value)) }
}

export function timeLabel(event: CalendarEvent, timeZone?: string) {
  if (event.all_day) {
    return event.end_date && event.end_date !== event.start_date ? `All day · through ${formatDate(event.end_date)}` : 'All day'
  }
  if (!event.start) return ''
  const start = clock(event.start, timeZone)
  if (!event.end || event.end === event.start) return start
  const sameDay = localDay(new Date(event.end), timeZone) === localDay(new Date(event.start), timeZone)
  return `${start} – ${clock(event.end, timeZone, !sameDay)}`
}

export function dayHeading(day: string, timeZone?: string, now = new Date()) {
  const today = localDay(now, timeZone)
  const tomorrow = localDay(new Date(now.getTime() + 86_400_000), timeZone)
  if (day === today) return 'Today'
  if (day === tomorrow) return 'Tomorrow'
  return formatDate(day, { weekday: 'long', month: 'long', day: 'numeric' })
}

/** Groups events (already in start order) by day, preserving order. */
export function groupByDay(events: CalendarEvent[], timeZone?: string) {
  const groups: { day: string; events: CalendarEvent[] }[] = []
  for (const event of events) {
    const day = eventDay(event, timeZone)
    const last = groups[groups.length - 1]
    if (last?.day === day) last.events.push(event)
    else groups.push({ day, events: [event] })
  }
  return groups
}
