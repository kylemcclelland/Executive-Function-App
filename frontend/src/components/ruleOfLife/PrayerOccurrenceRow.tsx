import { Link } from 'react-router-dom'
import { Check, Pencil, SkipForward } from 'lucide-react'
import { clockLabel, useMarkOccurrence } from '../../lib/ruleOfLife'
import type { RuleOccurrence } from '../../types/ruleOfLife'

/** One scheduled prayer on a day: its time, a link that opens the prayer, and the two simple marks (no streaks or scores). */
export function PrayerOccurrenceRow({ occurrence, showEdit = true }: { occurrence: RuleOccurrence; showEdit?: boolean }) {
  const mark = useMarkOccurrence()
  const set = (status: 'completed' | 'skipped') => mark.mutate({ entryId: occurrence.entry_id, date: occurrence.date, status: occurrence.status === status ? null : status })
  return <li className={`event-row event-prayer${occurrence.status ? ` is-${occurrence.status}` : ''}`}>
    <span className="event-time">{clockLabel(occurrence.local_time)}</span>
    <div className="event-main">
      <Link className="event-title" to={occurrence.link}>{occurrence.title}</Link>
      <small className="event-location">Rule of Life{occurrence.status ? ` · ${occurrence.status === 'completed' ? 'Completed' : 'Skipped'}` : ''}</small>
    </div>
    <span className="prayer-actions">
      <button type="button" className="prayer-mark" aria-pressed={occurrence.status === 'completed'} aria-label={`Mark ${occurrence.title} completed`} onClick={() => set('completed')} disabled={mark.isPending}><Check size={14} aria-hidden="true" /></button>
      <button type="button" className="prayer-mark" aria-pressed={occurrence.status === 'skipped'} aria-label={`Mark ${occurrence.title} skipped`} onClick={() => set('skipped')} disabled={mark.isPending}><SkipForward size={14} aria-hidden="true" /></button>
      {showEdit && <Link className="prayer-mark" to={`/rule-of-life?edit=${occurrence.entry_id}`} aria-label={`Edit ${occurrence.title}`}><Pencil size={14} aria-hidden="true" /></Link>}
    </span>
  </li>
}
