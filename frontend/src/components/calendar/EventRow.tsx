import { MapPin, Repeat } from 'lucide-react'
import { timeLabel } from '../../lib/calendar'
import type { CalendarEvent } from '../../types'

export function EventRow({ event, timeZone, prefix }: { event: CalendarEvent; timeZone?: string; prefix?: string }) {
  const link = event.html_link?.startsWith('https://') ? event.html_link : null
  return <li className="event-row">
    <span className="event-time">{prefix && <strong>{prefix}</strong>}{timeLabel(event, timeZone)}</span>
    <div className="event-main">
      {link ? <a href={link} target="_blank" rel="noopener noreferrer" className="event-title">{event.title}<span className="sr-only"> (opens in Google Calendar)</span></a> : <span className="event-title">{event.title}</span>}
      {event.location && <small className="event-location"><MapPin size={11} /> {event.location}</small>}
    </div>
    {event.recurring && <span className="event-repeat" title="Repeats" role="img" aria-label="Repeating event"><Repeat size={13} /></span>}
  </li>
}
