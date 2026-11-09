import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../../theme/theme'

/** Header shortcut: flips between Light and Dark. Choosing System lives in Preferences. */
export function ThemeToggle() {
  const { resolved, setPreference } = useTheme()
  const next = resolved === 'dark' ? 'light' : 'dark'
  return <button type="button" className="theme-toggle" onClick={() => setPreference(next)} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
    {resolved === 'dark' ? <Sun size={16} strokeWidth={1.7} /> : <Moon size={16} strokeWidth={1.7} />}
  </button>
}
