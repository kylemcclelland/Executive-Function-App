/** Which liturgical calendar Today shows, chosen on the Today card or in Preferences and remembered on this device. */
export type CalendarProvider = 'traditional' | 'current'
export const CALENDAR_PROVIDER_KEY = 'optima.calendar-provider'
export const PROVIDERS: { key: CalendarProvider; label: string }[] = [{ key: 'traditional', label: 'Traditional (1960)' }, { key: 'current', label: 'Current Roman' }]

/** The saved choice; the traditional calendar unless the reader chose the current one. */
export function savedProvider(): CalendarProvider {
  try { return window.localStorage.getItem(CALENDAR_PROVIDER_KEY) === 'current' ? 'current' : 'traditional' } catch { return 'traditional' }
}

export function saveProvider(next: CalendarProvider) {
  try { window.localStorage.setItem(CALENDAR_PROVIDER_KEY, next) } catch { /* the choice just is not remembered */ }
}
