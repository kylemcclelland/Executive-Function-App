import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Input } from '../components/ui'
import { ErrorMessage, Loading, PageHeader } from '../components/common'
import { api, ApiError } from '../services/api'
import { useAction } from '../hooks/useAction'
import { AppearanceCard } from '../components/brand/AppearanceCard'
import { AboutCard } from '../components/brand/AboutCard'

export function SettingsPage() {
  const query = useQuery({ queryKey: ['user'], queryFn: () => api<{ timezone: string }>('/user'), retry: false })
  const [timezone, setTimezone] = useState<string | null>(null)
  const [validationError, setValidationError] = useState('')
  const [saved, setSaved] = useState(false)
  const action = useAction()
  const unsupported = query.error instanceof ApiError && [404, 405].includes(query.error.status)
  return <><PageHeader eyebrow="PREFERENCES" title="Preferences">Your day follows your local date.</PageHeader><Card className="settings-card"><h2>Your timezone</h2><p className="muted">Today’s priorities follow your local date, not the server’s clock.</p>{query.isPending ? <Loading /> : unsupported ? <p>Timezone preferences aren’t supported by this server yet. Today uses the timezone shown on your Today page.</p> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : <form onSubmit={e => { e.preventDefault(); const value = timezone ?? query.data.timezone; try { new Intl.DateTimeFormat(undefined, { timeZone: value }).format() } catch { setValidationError('Please enter a valid IANA timezone, such as America/New_York.'); setSaved(false); return } setValidationError(''); void action.run(() => api('/user', 'PATCH', { timezone: value }), () => setSaved(true)) }}><label htmlFor="timezone">IANA timezone</label><Input id="timezone" list="timezones" placeholder="e.g. America/New_York" value={timezone ?? query.data.timezone} onChange={e => { setTimezone(e.target.value); setSaved(false) }} required /><datalist id="timezones">{['UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Europe/London', 'Europe/Paris', 'Asia/Kolkata', 'Asia/Tokyo', 'Australia/Sydney'].map(zone => <option key={zone} value={zone} />)}</datalist><Button disabled={action.pending}>{action.pending ? 'Saving…' : 'Save timezone'}</Button><div aria-live="polite">{saved && <p className="success-message">Timezone saved.</p>}</div><ErrorMessage message={validationError || action.error} /></form>}</Card><AppearanceCard /><AboutCard /></>
}
