import { describe, expect, it } from 'vitest'
import { TIMEZONE_OPTIONS, isValidZone, matchingOption, timezoneLabel } from '../lib/timezones'

describe('timezone options', () => {
  it('lists only valid IANA identifiers, each with a unique friendly label', () => {
    for (const option of TIMEZONE_OPTIONS) expect(isValidZone(option.value)).toBe(true)
    expect(new Set(TIMEZONE_OPTIONS.map(o => o.label)).size).toBe(TIMEZONE_OPTIONS.length)
    expect(TIMEZONE_OPTIONS.every(o => !o.label.includes('/'))).toBe(true)
  })
  it('maps aliases to the listed option and labels unlisted zones readably', () => {
    expect(matchingOption('UTC')?.value).toBe('Etc/UTC')
    expect(timezoneLabel('America/New_York')).toBe('Eastern Time (US & Canada)')
    expect(timezoneLabel('Asia/Kolkata')).toMatch(/Kolkata/)
    expect(timezoneLabel('Asia/Kolkata')).not.toBe('Asia/Kolkata')
    expect(isValidZone('Definitely/Invalid')).toBe(false)
  })
  it('relies on the tz database for daylight saving (New York is UTC-5 in January, UTC-4 in July)', () => {
    const hour = (iso: string) => Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' }).format(new Date(iso)))
    expect(hour('2026-01-15T12:00:00Z')).toBe(7)
    expect(hour('2026-07-15T12:00:00Z')).toBe(8)
  })
})
