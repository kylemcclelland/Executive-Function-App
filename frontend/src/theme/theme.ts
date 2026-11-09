import { useSyncExternalStore } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

/** The same key and rules as the inline script in index.html, which runs before first paint. */
export const THEME_KEY = 'optima-pars-theme'
const THEME_COLORS: Record<ResolvedTheme, string> = { light: '#F7F3EA', dark: '#111B17' }
const DARK_QUERY = '(prefers-color-scheme: dark)'

function readStored(): ThemePreference {
  try {
    const value = window.localStorage.getItem(THEME_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch { return 'system' }
}

function systemPrefersDark() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(DARK_QUERY).matches
}

export function resolveTheme(preference: ThemePreference, systemDark = systemPrefersDark()): ResolvedTheme {
  return preference === 'dark' || (preference === 'system' && systemDark) ? 'dark' : 'light'
}

let preference: ThemePreference = readStored()
const listeners = new Set<() => void>()
const notify = () => listeners.forEach(listener => listener())

function apply() {
  const resolved = resolveTheme(preference)
  const root = document.documentElement
  root.setAttribute('data-theme', resolved)
  root.style.colorScheme = resolved
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[resolved])
}

/** Sets the preference, remembers it on this device, and applies it everywhere at once. */
export function setThemePreference(next: ThemePreference) {
  preference = next
  try { window.localStorage.setItem(THEME_KEY, next) } catch { /* the choice still applies for this session */ }
  apply()
  notify()
}

/** Call once at startup: applies the theme and follows the operating system and other tabs. */
export function initTheme() {
  preference = readStored()
  apply()
  if (typeof window.matchMedia === 'function') {
    window.matchMedia(DARK_QUERY).addEventListener('change', () => { apply(); notify() })
  }
  window.addEventListener('storage', event => {
    if (event.key === THEME_KEY) { preference = readStored(); apply(); notify() }
  })
}

// One primitive snapshot, so React re-renders when the preference or the system setting changes.
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }
const snapshot = () => `${preference}|${systemPrefersDark()}`

export function useTheme() {
  const [current, systemDark] = useSyncExternalStore(subscribe, snapshot, snapshot).split('|')
  const value = current as ThemePreference
  return { preference: value, resolved: resolveTheme(value, systemDark === 'true'), setPreference: setThemePreference }
}
