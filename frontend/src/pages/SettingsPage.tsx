import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card } from '../components/ui'
import { ErrorMessage, Loading, PageHeader } from '../components/common'
import { api, ApiError } from '../services/api'
import { useAction } from '../hooks/useAction'
import { AppearanceCard } from '../components/brand/AppearanceCard'
import { AboutCard } from '../components/brand/AboutCard'
import { PROVIDERS, saveProvider, savedProvider, type CalendarProvider } from '../lib/calendarProvider'
import { TIMEZONE_OPTIONS, deviceZone, isValidZone, matchingOption, timezoneLabel } from '../lib/timezones'

export function SettingsPage() {
  return <><PageHeader eyebrow="PREFERENCES" title="Preferences">Your day follows your local date.</PageHeader><CalendarTimeCard /><AppearanceCard /><AboutCard /></>
}

/** Timezone (saved on the server, per account) and the liturgical calendar shown on Today (remembered on this device). */
function CalendarTimeCard() {
  const query = useQuery({ queryKey: ['user'], queryFn: () => api<{ timezone: string }>('/user'), retry: false })
  const unsupported = query.error instanceof ApiError && [404, 405].includes(query.error.status)
  return <Card className="settings-card calendar-time-card">
    <h2>Calendar &amp; Time</h2>
    <p className="muted">Today’s priorities follow your local date, not the server’s clock.</p>
    {query.isPending ? <Loading /> : unsupported ? <p>Timezone preferences aren’t supported by this server yet. Today uses the timezone shown on your Today page.</p> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : <TimezoneForm saved={query.data.timezone} />}
    <LiturgicalCalendarChoice />
  </Card>
}

function TimezoneForm({ saved }: { saved: string }) {
  // The select holds a listed option's identifier, or the saved identifier itself when it is valid but not listed, so it is never silently changed.
  const savedValue = matchingOption(saved)?.value ?? saved
  const [draft, setDraft] = useState<string | null>(null)
  const [savedNotice, setSavedNotice] = useState(false)
  const action = useAction()
  const value = draft ?? savedValue
  const options = matchingOption(saved) || !isValidZone(saved) ? TIMEZONE_OPTIONS : [{ value: saved, label: timezoneLabel(saved) }, ...TIMEZONE_OPTIONS]
  const device = deviceZone()
  const deviceValue = device && (matchingOption(device)?.value ?? device)
  const offerDevice = deviceValue && deviceValue !== value && deviceValue !== savedValue
  function save(event: React.FormEvent) {
    event.preventDefault()
    if (!isValidZone(value)) return
    setSavedNotice(false)
    void action.run(() => api('/user', 'PATCH', { timezone: value }), () => { setDraft(null); setSavedNotice(true) })
  }
  return <form onSubmit={save}>
    <label htmlFor="timezone">Time Zone</label>
    <select id="timezone" className="input" value={value} aria-describedby="timezone-hint" onChange={e => { setDraft(e.target.value); setSavedNotice(false) }}>
      {!isValidZone(saved) && <option value={saved} disabled>Choose a time zone</option>}
      {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
    <p className="muted" id="timezone-hint"><em>Your calendar and daily schedule will follow this timezone.</em></p>
    {offerDevice && <p className="muted timezone-device">This device is set to {timezoneLabel(device)}. <Button type="button" variant="ghost" size="sm" onClick={() => { setDraft(deviceValue); setSavedNotice(false) }}>Use this device’s time zone</Button></p>}
    <Button disabled={action.pending || value === savedValue}>{action.pending ? 'Saving…' : 'Save timezone'}</Button>
    <div aria-live="polite">{savedNotice && <p className="success-message">Timezone saved: {timezoneLabel(saved)}.</p>}</div>
    {action.error && <ErrorMessage message={`Couldn’t save your time zone; ${timezoneLabel(saved)} is still in effect. ${action.error}`} />}
  </form>
}

function LiturgicalCalendarChoice() {
  const [provider, setProvider] = useState<CalendarProvider>(savedProvider)
  return <fieldset className="theme-choice calendar-choice">
    <legend>Liturgical calendar</legend>
    <p className="muted">The calendar shown on Today. Remembered on this device.</p>
    {PROVIDERS.map(item => <label key={item.key} className="theme-option">
      <input type="radio" name="calendar-provider" value={item.key} checked={provider === item.key} onChange={() => { setProvider(item.key); saveProvider(item.key) }} />
      <span className="theme-option-label">{item.label}</span>
    </label>)}
  </fieldset>
}
