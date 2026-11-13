import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card } from '../components/ui'
import { ErrorMessage, Loading, PageHeader } from '../components/common'
import { api, ApiError } from '../services/api'
import { useAction } from '../hooks/useAction'
import { useInstallPrompt } from '../hooks/useInstallPrompt'
import { AppearanceCard } from '../components/brand/AppearanceCard'
import { AboutCard } from '../components/brand/AboutCard'
import { PROVIDERS, saveProvider, savedProvider, type CalendarProvider } from '../lib/calendarProvider'
import { useQueryClient } from '@tanstack/react-query'
import { TIMEZONE_OPTIONS, deviceZone, isValidZone, matchingOption, timezoneLabel } from '../lib/timezones'

export function SettingsPage() {
  return <><PageHeader eyebrow="PREFERENCES" title="Preferences">Your day follows your local date.</PageHeader><CalendarTimeCard /><AppearanceCard /><InstallCard /><AboutCard /></>
}

/** "Install Optima Pars": a real install button where the browser offers one, Add-to-Home-Screen
 * guidance on iOS, and nothing at all inside the installed app itself. A regular browser window
 * cannot reliably tell that the app is installed elsewhere, so it may still show this card. */
export function InstallCard() {
  const { standalone, canPrompt, install, ios } = useInstallPrompt()
  if (standalone) return null
  return <Card className="settings-card">
    <h2>Install Optima Pars</h2>
    {canPrompt ? <>
      <p className="muted">Install the app for its own window, a home-screen icon and faster starts. Your account and data stay exactly the same.</p>
      <p><Button onClick={() => void install()}>Install Optima Pars</Button></p>
    </> : ios ? <>
      <p className="muted">On iPhone and iPad, install from Safari's share menu:</p>
      <p className="muted"><strong>Share</strong> → <strong>Add to Home Screen</strong>. Other iOS browsers keep this under their own menu, and some versions label it "Add to Dock" on iPad.</p>
    </> : <p className="muted">Your browser hasn't offered installation on this page. Chrome and Edge show an install icon in the address bar or menu; if the app is already installed, open it from where your apps live.</p>}
  </Card>
}

/** Timezone (saved on the server, per account) and the liturgical calendar shown on Today (remembered on this device). */
function CalendarTimeCard() {
  const query = useQuery({ queryKey: ['user'], queryFn: () => api<{ timezone: string }>('/user'), retry: false })
  const unsupported = query.error instanceof ApiError && [404, 405].includes(query.error.status)
  return <Card className="settings-card calendar-time-card">
    <h2>Calendar &amp; Time</h2>
    <p className="muted">Today’s priorities follow your local date, not the server’s clock.</p>
    {query.isPending ? <Loading /> : unsupported ? <p>Timezone preferences aren’t supported by this server yet. Today uses the timezone shown on your Today page.</p> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : <TimezoneForm saved={query.data.timezone} />}
    <LiturgicalCalendarChoice saved={query.data && 'calendar_provider' in query.data ? (query.data as { calendar_provider?: CalendarProvider | null }).calendar_provider : undefined} />
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

function LiturgicalCalendarChoice({ saved }: { saved?: CalendarProvider | null }) {
  const client = useQueryClient()
  const [fallback, setFallback] = useState<CalendarProvider>(savedProvider)
  const action = useAction()
  const provider = saved ?? fallback
  function choose(next: CalendarProvider) {
    setFallback(next)
    saveProvider(next)                                   // the device remembers even offline
    void action.run(() => api('/user', 'PATCH', { calendar_provider: next }), () => {
      client.setQueryData(['user'], (old: object | undefined) => (old ? { ...old, calendar_provider: next } : old))
    })
  }
  return <div>
    <label htmlFor="default-calendar">Default Calendar</label>
    <select id="default-calendar" className="input" value={provider} aria-describedby="default-calendar-hint"
      onChange={e => choose(e.target.value as CalendarProvider)}>
      {PROVIDERS.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
    </select>
    <p id="default-calendar-hint" className="muted">The calendar Today shows. Saved to your account, on every device.</p>
    <ErrorMessage message={action.error} />
  </div>
}
