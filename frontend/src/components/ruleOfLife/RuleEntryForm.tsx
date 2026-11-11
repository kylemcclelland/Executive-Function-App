import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Dialog } from '../ui'
import { ErrorMessage } from '../common'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { isoDate } from '../../lib/divineOffice'
import { WEEKDAY_NAMES, browserZone } from '../../lib/ruleOfLife'
import { isValidZone, timezoneLabel } from '../../lib/timezones'
import type { DevotionBrief } from '../../types/devotions'
import type { RuleDraft, RuleEntry, RuleKind, RuleRecurrence } from '../../types/ruleOfLife'

interface HourInfo { slug: string; name: string; latin: string; available: boolean }

/** Adds a prayer to the Rule of Life in four steps, or edits when and how often an existing one recurs (the prayer itself cannot be changed). */
export function RuleEntryForm({ entry, onClose }: { entry?: RuleEntry; onClose: () => void }) {
  const action = useAction()
  const [kind, setKind] = useState<RuleKind>('office_hour')
  const [ref, setRef] = useState('')
  const [search, setSearch] = useState('')
  const [time, setTime] = useState(entry?.local_time ?? '07:00')
  const [recurrence, setRecurrence] = useState<RuleRecurrence>(entry?.recurrence ?? 'daily')
  const [weekdays, setWeekdays] = useState<number[]>(entry?.weekdays ?? [])
  const [date, setDate] = useState(() => entry?.start_date ?? isoDate(new Date()))
  const [notify, setNotify] = useState(entry?.notify ?? false)
  const hours = useQuery({ queryKey: ['office-hours'], queryFn: () => api<HourInfo[]>('/divine-office/hours'), retry: false, enabled: !entry })
  // New entries follow the timezone chosen in Preferences; an existing entry keeps the zone it was scheduled in.
  const preferredZone = useQuery({ queryKey: ['user'], queryFn: () => api<{ timezone: string }>('/user'), retry: false, enabled: !entry }).data?.timezone
  const zone = entry?.timezone ?? (preferredZone && isValidZone(preferredZone) ? preferredZone : browserZone())
  const devotions = useQuery({ queryKey: ['devotions'], queryFn: () => api<DevotionBrief[]>('/devotions'), retry: false, enabled: !entry })
  const matches = useMemo(() => {
    const words = search.trim().toLowerCase()
    return (devotions.data ?? []).filter(item => !words || `${item.title} ${item.subtitle ?? ''}`.toLowerCase().includes(words))
  }, [devotions.data, search])
  const toggle = (day: number) => setWeekdays(current => current.includes(day) ? current.filter(d => d !== day) : [...current, day].sort())
  const ready = time && (entry || ref) && (recurrence !== 'weekly' || weekdays.length > 0) && (recurrence !== 'once' || date)

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const schedule = { local_time: time, timezone: zone, recurrence, weekdays: recurrence === 'weekly' ? weekdays : [], start_date: recurrence === 'once' ? date : entry?.start_date ?? null, notify }
    void action.run(() => entry ? api(`/rule-of-life/${entry.id}`, 'PATCH', schedule) : api('/rule-of-life', 'POST', { kind, ref, ...schedule } satisfies RuleDraft), onClose)
  }

  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={entry ? 'Edit Rule of Life entry' : 'Add to Rule of Life'} description={entry ? entry.title : 'Choose a prayer, then when you want to pray it.'}>
    <form onSubmit={submit} className="rule-form">
      {!entry && <>
        <fieldset className="rule-step"><legend><span className="rule-step-number" aria-hidden="true">1</span> What would you like to pray?</legend>
          <label className="rule-choice"><input type="radio" name="rule-kind" checked={kind === 'office_hour'} onChange={() => { setKind('office_hour'); setRef('') }} /> The Divine Office</label>
          <label className="rule-choice"><input type="radio" name="rule-kind" checked={kind === 'devotion'} onChange={() => { setKind('devotion'); setRef('') }} /> A devotion, such as the Rosary</label>
        </fieldset>
        {kind === 'office_hour' ? <fieldset className="rule-step"><legend><span className="rule-step-number" aria-hidden="true">2</span> Which hour?</legend>
          {hours.isPending ? <p className="muted" role="status">Loading the hours…</p> : hours.isError ? <ErrorMessage message="The hours could not be loaded." /> :
            <div className="rule-options">{hours.data.map(hour => <label key={hour.slug} className="rule-option"><input type="radio" name="rule-prayer" value={hour.slug} checked={ref === hour.slug} disabled={!hour.available} onChange={() => setRef(hour.slug)} /> <span>{hour.name} <small lang="la">{hour.latin}</small></span></label>)}</div>}
          <p className="muted">Each day shows that day’s own Office.</p>
        </fieldset> : <fieldset className="rule-step"><legend><span className="rule-step-number" aria-hidden="true">2</span> Which devotion?</legend>
          {devotions.isPending ? <p className="muted" role="status">Loading the devotions…</p> : devotions.isError ? <ErrorMessage message="The devotions could not be loaded." /> :
            devotions.data.length === 0 ? <p className="muted">No devotions are available in The Oratory yet.</p> : <>
              <label className="rule-search">Search devotions<input className="input" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="For example, Rosary" /></label>
              <p className="muted" role="status">{matches.length === 0 ? 'No devotion matches your search.' : `${matches.length} ${matches.length === 1 ? 'devotion' : 'devotions'}`}</p>
              <div className="rule-options rule-scroll">{matches.map(item => <label key={item.slug} className="rule-option"><input type="radio" name="rule-prayer" value={item.slug} checked={ref === item.slug} onChange={() => setRef(item.slug)} /> <span>{item.title}</span></label>)}</div>
            </>}
        </fieldset>}
      </>}
      <fieldset className="rule-step"><legend><span className="rule-step-number" aria-hidden="true">{entry ? 1 : 3}</span> When?</legend>
        <div className="form-grid">
          <label>Time<input className="input" type="time" value={time} onChange={event => setTime(event.target.value)} required /></label>
          <label>Repeats<select className="input" value={recurrence} onChange={event => setRecurrence(event.target.value as RuleRecurrence)}>
            <option value="daily">Every day</option><option value="weekly">On chosen weekdays</option><option value="once">Once</option></select></label>
          {recurrence === 'once' && <label className="full">Date<input className="input" type="date" value={date} onChange={event => setDate(event.target.value)} required /></label>}
          {recurrence === 'weekly' && <div className="full rule-weekdays" role="group" aria-label="Weekdays">{WEEKDAY_NAMES.map((name, day) => <label key={name} className="rule-weekday"><input type="checkbox" checked={weekdays.includes(day)} onChange={() => toggle(day)} aria-label={name} />{name.slice(0, 3)}</label>)}</div>}
        </div>
        <details className="rule-more"><summary>More options</summary>
          <label className="rule-notify"><input type="checkbox" checked={notify} onChange={event => setNotify(event.target.checked)} /> Remind me <small>(your preference is saved; notifications are not delivered yet)</small></label>
          <p className="muted">Time zone: {timezoneLabel(zone)}</p>
        </details>
      </fieldset>
      <ErrorMessage message={action.error} />
      <div className="dialog-actions"><Button type="button" variant="outline" onClick={onClose} disabled={action.pending}>Cancel</Button><Button type="submit" disabled={action.pending || !ready}>{action.pending ? 'Saving…' : entry ? 'Save changes' : 'Save to Rule of Life'}</Button></div>
    </form>
  </Dialog>
}
