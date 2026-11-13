/** Friendly timezone names shown to people; the IANA identifier is what the server stores. Daylight saving comes from the platform's tz database. */
export const TIMEZONE_OPTIONS: { value: string; label: string }[] = [
  { value: 'America/New_York', label: 'Eastern Time (US & Canada)' },
  { value: 'America/Chicago', label: 'Central Time (US & Canada)' },
  { value: 'America/Denver', label: 'Mountain Time (US & Canada)' },
  { value: 'America/Phoenix', label: 'Arizona Time' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada)' },
  { value: 'America/Anchorage', label: 'Alaska Time' },
  { value: 'Pacific/Honolulu', label: 'Hawaii Time' },
  { value: 'America/Halifax', label: 'Atlantic Time' },
  { value: 'Etc/UTC', label: 'Coordinated Universal Time (UTC)' },
  { value: 'Europe/London', label: 'London' },
  { value: 'Europe/Dublin', label: 'Dublin' },
  { value: 'Europe/Rome', label: 'Central European Time (Rome, Paris, Berlin)' },
  { value: 'Europe/Madrid', label: 'Madrid' },
  { value: 'America/Mexico_City', label: 'Mexico City' },
  { value: 'America/Sao_Paulo', label: 'São Paulo' },
  { value: 'Asia/Tokyo', label: 'Tokyo' },
  { value: 'Asia/Singapore', label: 'Singapore' },
  { value: 'Australia/Sydney', label: 'Sydney' },
]

/** Identifiers that name the same zone as a listed option (the server's default is plain "UTC"). */
const ALIASES: Record<string, string> = { UTC: 'Etc/UTC', 'Etc/GMT': 'Etc/UTC', GMT: 'Etc/UTC', 'Etc/Universal': 'Etc/UTC', 'Etc/Zulu': 'Etc/UTC', 'US/Eastern': 'America/New_York', 'US/Central': 'America/Chicago', 'US/Mountain': 'America/Denver', 'US/Arizona': 'America/Phoenix', 'US/Pacific': 'America/Los_Angeles', 'US/Alaska': 'America/Anchorage', 'US/Hawaii': 'Pacific/Honolulu', 'Asia/Calcutta': 'Asia/Kolkata' }

export function isValidZone(zone: string) {
  if (!zone) return false
  try { new Intl.DateTimeFormat('en-US', { timeZone: zone }).format(); return true } catch { return false }
}

/** The listed option a saved identifier corresponds to, if any. */
export function matchingOption(zone: string) {
  const value = ALIASES[zone] ?? zone
  return TIMEZONE_OPTIONS.find(option => option.value === value)
}

/** A readable name for any valid zone: the listed label, else the zone's generic name and city (e.g. "India Standard Time (Kolkata)"). */
export function timezoneLabel(zone: string) {
  const option = matchingOption(zone)
  if (option) return option.label
  const city = (zone.split('/').pop() ?? zone).replaceAll('_', ' ')
  try {
    const name = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'longGeneric' }).formatToParts(new Date()).find(part => part.type === 'timeZoneName')?.value
    if (name && !/^GMT/.test(name)) return name === city ? city : `${name} (${city})`
  } catch { /* fall through to the city alone */ }
  return city
}

/** The device's timezone when it is valid; never saved automatically, only offered. */
export function deviceZone() {
  try { const zone = Intl.DateTimeFormat().resolvedOptions().timeZone; return zone && isValidZone(zone) ? zone : null } catch { return null }
}
