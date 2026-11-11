import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Bell, BellOff, HandHeart, Pause, Pencil, Play, Plus, Trash2 } from 'lucide-react'
import { Button, Card } from '../components/ui'
import { ConfirmDelete, Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { RuleEntryForm } from '../components/ruleOfLife/RuleEntryForm'
import { NotificationSettings } from '../components/ruleOfLife/NotificationSettings'
import { api } from '../services/api'
import { useAction } from '../hooks/useAction'
import { clockLabel, describeRecurrence, entryLink, kindLabel, useMarkOccurrence, useRuleEntries, useRuleOccurrences } from '../lib/ruleOfLife'
import { isoDate } from '../lib/divineOffice'
import type { RuleEntry } from '../types/ruleOfLife'

/** The user's Rule of Life: their scheduled prayers in the order of the day, with the same entries shown on the Calendar. */
export function RuleOfLifePage() {
  const entries = useRuleEntries()
  const [params, setParams] = useSearchParams()
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<RuleEntry | null>(null)
  const pause = useAction()
  const mark = useMarkOccurrence()
  const [todayDate] = useState(() => new Date())
  const todays = useRuleOccurrences(todayDate, 1)
  const today = isoDate(todayDate)
  const editing = entries.data?.find(entry => entry.id === params.get('edit'))
  const closeEdit = () => { const next = new URLSearchParams(params); next.delete('edit'); setParams(next, { replace: true }) }
  return <>
    <PageHeader eyebrow="ORA ET LABORA" title="Rule of Life" action={<Button onClick={() => setAdding(true)}><Plus size={15} aria-hidden="true" /> Add to Rule of Life</Button>}>
      Your daily prayers, each at its own time. They also appear on your Calendar. <Link className="rule-back" to="/devotions">Back to The Oratory</Link>
    </PageHeader>
    {entries.isPending ? <Loading /> : entries.isError ? <Card><ErrorMessage message={entries.error.message} /><Button variant="outline" onClick={() => void entries.refetch()}>Try again</Button></Card> :
      entries.data.length === 0 ? <Card><Empty title="Your Rule of Life is empty">Add a Divine Office hour, a saved prayer or the Holy Rosary, and choose when you will pray it.</Empty></Card> :
        <Card className="rule-card"><ul className="rule-list" aria-label="Rule of Life">
          {entries.data.map(entry => {
            const occurrence = todays.data?.find(item => item.entry_id === entry.id)
            return <li key={entry.id} className={`rule-entry${entry.active ? '' : ' is-paused'}`}>
              <span className="rule-time">{clockLabel(entry.local_time)}</span>
              <div className="rule-main">
                {entry.available ? <Link className="rule-title" to={entryLink(entry, today)}>{entry.title}</Link> : <span className="rule-title">{entry.title}</span>}
                <small>{kindLabel(entry.kind)} · {describeRecurrence(entry)} · {entry.timezone}</small>
                <small className="rule-notify-status">{entry.notify ? <><Bell size={11} aria-hidden="true" /> Reminder on (not delivered yet)</> : <><BellOff size={11} aria-hidden="true" /> No reminder</>}{!entry.active && ' · Paused'}{!entry.available && ' · This prayer is no longer available'}</small>
                {occurrence && <span className="rule-today">Today: {occurrence.status ? (occurrence.status === 'completed' ? 'Completed' : 'Skipped') : 'not yet marked'}
                  <button type="button" className="prayer-mark" aria-pressed={occurrence.status === 'completed'} onClick={() => mark.mutate({ entryId: entry.id, date: today, status: occurrence.status === 'completed' ? null : 'completed' })}>Completed</button>
                  <button type="button" className="prayer-mark" aria-pressed={occurrence.status === 'skipped'} onClick={() => mark.mutate({ entryId: entry.id, date: today, status: occurrence.status === 'skipped' ? null : 'skipped' })}>Skipped</button></span>}
              </div>
              <div className="rule-actions">
                <Button variant="ghost" size="sm" onClick={() => setParams({ edit: entry.id })} aria-label={`Edit ${entry.title}`}><Pencil size={14} aria-hidden="true" /> Edit</Button>
                <Button variant="ghost" size="sm" disabled={pause.pending} onClick={() => void pause.run(() => api(`/rule-of-life/${entry.id}`, 'PATCH', { active: !entry.active }))} aria-label={`${entry.active ? 'Pause' : 'Resume'} ${entry.title}`}>{entry.active ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />} {entry.active ? 'Pause' : 'Resume'}</Button>
                <Button variant="ghost" size="sm" onClick={() => setRemoving(entry)} aria-label={`Remove ${entry.title}`}><Trash2 size={14} aria-hidden="true" /> Remove</Button>
              </div>
            </li>
          })}
        </ul><ErrorMessage message={pause.error} />
        <p className="muted rule-note"><HandHeart size={13} aria-hidden="true" /> Marking a prayer completed or skipped is only for you: there are no streaks or scores.</p></Card>}
    <NotificationSettings />
    {adding && <RuleEntryForm onClose={() => setAdding(false)} />}
    {editing && <RuleEntryForm entry={editing} onClose={closeEdit} />}
    {removing && <ConfirmDelete title={removing.title} onDelete={() => api(`/rule-of-life/${removing.id}`, 'DELETE')} onClose={() => setRemoving(null)} />}
  </>
}
