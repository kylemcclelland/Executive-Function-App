import { Monitor, Moon, Sun, type LucideIcon } from 'lucide-react'
import { Card } from '../ui'
import { useTheme, type ThemePreference } from '../../theme/theme'

const OPTIONS: { value: ThemePreference; label: string; icon: LucideIcon; hint: string }[] = [
  { value: 'light', label: 'Light', icon: Sun, hint: 'Warm ivory, like a page in daylight' },
  { value: 'dark', label: 'Dark', icon: Moon, hint: 'A monastic library at night' },
  { value: 'system', label: 'System', icon: Monitor, hint: 'Follow this device' },
]

export function AppearanceCard() {
  const { preference, resolved, setPreference } = useTheme()
  return <Card className="settings-card appearance-card">
    <h2>Appearance</h2>
    <p className="muted">Choose how Optima Pars looks. Your choice is remembered on this device.</p>
    <fieldset className="theme-choice">
      <legend className="sr-only">Theme</legend>
      {OPTIONS.map(({ value, label, icon: Icon, hint }) => <label key={value} className="theme-option">
        <input type="radio" name="theme" value={value} checked={preference === value} onChange={() => setPreference(value)} />
        <Icon size={18} strokeWidth={1.6} aria-hidden="true" /><span className="theme-option-label">{label}</span><small>{hint}</small>
      </label>)}
    </fieldset>
    <p className="muted" aria-live="polite">{preference === 'system' ? `Following your device: currently ${resolved}.` : `Using the ${resolved} theme.`}</p>
  </Card>
}
