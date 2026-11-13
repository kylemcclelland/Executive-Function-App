import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CALENDAR_PROVIDER_KEY, LiturgicalCalendarCard } from '../components/today/LiturgicalCalendarCard'
import { ROMCAL_VERSION, currentRomanDay, nameTokens, sameSaint } from '../lib/romcalCalendar'
import { isoDate } from '../lib/divineOffice'
import type { CalendarDay } from '../types/liturgicalCalendar'

// Neutral filler for the traditional side; the modern celebrations below come from Romcal itself.
const engine = { name: 'Divinum Officium', url: 'https://example.invalid', commit: null, version: 'Rubrics 1960 - 1960' }
const traditional = (celebration: string, extra: Partial<CalendarDay> = {}): CalendarDay => ({
  date: '2026-11-10', edition: 'roman_1960', celebration, celebration_latin: 'S. Fillerii', celebration_source: 'upstream_english', designation: null, celebration_type: 'saint', type_label: 'Saint',
  qualifier: null, rank: 'III. classis', rank_class: 'III', rank_label: 'III Class', season: 'Time after Pentecost', season_code: 'Pent23', commemorations: [],
  description: { text: 'Filler was born in a small town. He served the poor.', source: { name: 'The Roman Breviary, Matins lesson', reference: 'Matins, Reading 3 (verbatim)', note: '' } }, engine, ...extra,
})
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
let requests: string[]

function mount(answer: () => Response | Promise<Response>) {
  requests = []
  vi.stubGlobal('fetch', vi.fn(async (input: string) => { const url = input.replace('/api', ''); if (url !== '/user') requests.push(url); return answer() }))   // the account-preference lookup is not under test here
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><LiturgicalCalendarCard /></MemoryRouter></QueryClientProvider>)
}
const heading = (name: string | RegExp) => screen.findByRole('heading', { name }, { timeout: 20000 })

beforeEach(() => { window.localStorage.clear(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(2026, 10, 10, 12, 0)) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); window.localStorage.clear() })

describe('the current Roman calendar (Romcal, United States propers), 2026', () => {
  const cases: [string, RegExp, string, string | null][] = [
    ['2026-01-01', /Mary, the Holy Mother of God|Mother of God/, 'Solemnity', 'White'],
    ['2026-03-19', /Joseph/, 'Solemnity', 'White'],
    ['2026-04-05', /Easter Sunday/, 'Solemnity', 'White'],
    ['2026-08-15', /Assumption/, 'Solemnity', 'White'],
    ['2026-11-01', /All Saints/, 'Solemnity', 'White'],
    ['2026-11-10', /Leo the Great/, 'Memorial', 'White'],
    ['2026-12-08', /Immaculate Conception.*Patroness of the USA/, 'Solemnity', 'White'],
    ['2026-12-25', /Nativity of the Lord/, 'Solemnity', 'White'],
  ]
  it.each(cases)('%s matches the USCCB 2026 calendar', async (date, name, rank, color) => {
    const day = await currentRomanDay(date)
    expect(day?.name).toMatch(name)
    expect([day?.rankLabel, day?.color]).toEqual([rank, color])
  }, 20000)

  it('labels Sundays, ferias and Lent, and lists optional memorials separately', async () => {
    expect(await currentRomanDay('2026-11-08')).toMatchObject({ rankLabel: 'Sunday', color: 'Green', season: 'Ordinary Time' })
    expect(await currentRomanDay('2026-02-18')).toMatchObject({ rankLabel: 'Feria', color: 'Violet', season: 'Lent' })
    expect(await currentRomanDay('2026-08-12')).toMatchObject({ rankLabel: 'Feria', optionalMemorials: [{ name: 'Saint Jane Frances de Chantal, Religious' }] })
  })

  it('applies United States propers and transfers, not the universal calendar', async () => {
    expect((await currentRomanDay('2026-01-04'))?.name).toMatch(/Epiphany/)                 // transferred to Sunday in the US (6 January is a Tuesday)
    expect((await currentRomanDay('2026-05-17'))?.name).toMatch(/Ascension/)                // Ascension on the Seventh Sunday of Easter
    expect((await currentRomanDay('2026-12-08'))?.calendarId).toBe('united_states')
  })
})

describe('reusing a traditional description', () => {
  const leo = async () => (await currentRomanDay('2026-11-10'))!
  it('requires the same saint, not merely the same date', async () => {
    expect(sameSaint(await leo(), traditional('St. Andrew Avellino'))).toBe(false)
    expect(sameSaint(await leo(), traditional('St. Leo I the Great'))).toBe(true)         // title words, accents and Roman numerals do not matter
    expect(sameSaint(await leo(), traditional('St. Leo II'))).toBe(false)                 // a different Leo
    expect(sameSaint(await leo(), traditional('St. Leo the Great', { description: null }))).toBe(false)
    expect(sameSaint(await leo(), traditional('St. Leo the Great', { celebration_type: 'feria' }))).toBe(false)
    expect(sameSaint(await leo(), undefined)).toBe(false)
    expect(nameTokens('Saint Thérèse of the Child Jesus, Virgin and Doctor of the Church')).toEqual(['therese', 'child', 'jesus'])
  })
})

describe('the calendar selector on the Today card', () => {
  it('defaults to the traditional calendar, with its Divine Office link and no Romcal request', async () => {
    mount(() => json(traditional('St. Andrew Avellino')))
    expect(await heading('St. Andrew Avellino')).toBeInTheDocument()
    expect(screen.getByText('Traditional Liturgical Calendar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Traditional (1960)' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Current Roman' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('link', { name: /Read Today’s Divine Office/ })).toHaveAttribute('href', '/divine-office?date=2026-11-10')
  })

  it('switches to the current calendar with its own name, rank, season and colour, and offers no traditional Office link', async () => {
    mount(() => json(traditional('St. Andrew Avellino')))
    await userEvent.click(screen.getByRole('button', { name: 'Current Roman' }))
    expect(await heading(/Leo the Great/)).toBeInTheDocument()
    expect(screen.getByText('Current Roman Calendar')).toBeInTheDocument()
    expect(screen.getByText('Memorial')).toBeInTheDocument()
    expect(screen.getByText('Ordinary Time · White vestments')).toBeInTheDocument()
    expect(screen.getByText(/Calendar: Romcal/).textContent).toContain(ROMCAL_VERSION)
    expect(screen.queryByRole('link', { name: /Divine Office/ })).toBeNull()
    expect(document.querySelector('.calendar-description')).toBeNull()                    // Andrew Avellino's lesson is not Leo's
    expect(screen.queryByText('St. Andrew Avellino')).toBeNull()                           // the providers are not mixed
  }, 30000)

  it('shows the traditional description with the current celebration only when it is the same saint, keeping its source', async () => {
    mount(() => json(traditional('St. Leo I the Great')))
    await userEvent.click(screen.getByRole('button', { name: 'Current Roman' }))
    expect(await screen.findByText('Filler was born in a small town. He served the poor.', {}, { timeout: 20000 })).toBeInTheDocument()
    expect(screen.getByText(/Traditional Breviary lesson\. Source: The Roman Breviary/)).toHaveAttribute('title', expect.stringContaining('verbatim'))
  }, 30000)

  it('still shows the current calendar, with no description, when the traditional engine is unavailable', async () => {
    mount(() => json({ detail: 'unavailable' }, 503))
    await userEvent.click(screen.getByRole('button', { name: 'Current Roman' }))
    expect(await heading(/Leo the Great/)).toBeInTheDocument()
    expect(document.querySelector('.calendar-description')).toBeNull()
  }, 30000)

  it('remembers the choice and restores it on the next visit', async () => {
    const first = mount(() => json(traditional('St. Andrew Avellino')))
    await userEvent.click(screen.getByRole('button', { name: 'Current Roman' }))
    expect(window.localStorage.getItem(CALENDAR_PROVIDER_KEY)).toBe('current')
    first.unmount()
    mount(() => json(traditional('St. Andrew Avellino')))
    expect(await heading(/Leo the Great/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Traditional (1960)' }))
    expect(window.localStorage.getItem(CALENDAR_PROVIDER_KEY)).toBe('traditional')
    expect(await heading('St. Andrew Avellino')).toBeInTheDocument()
  }, 40000)

  it('uses the reader’s local date for both calendars, never UTC', async () => {
    vi.setSystemTime(new Date(2026, 11, 8, 23, 45))                                        // 8 December, late evening local time
    window.localStorage.setItem(CALENDAR_PROVIDER_KEY, 'current')
    mount(() => json(traditional('St. Andrew Avellino')))
    expect(await heading(/Immaculate Conception/)).toBeInTheDocument()
    expect(requests[0]).toBe(`/liturgical-calendar/${isoDate(new Date(2026, 11, 8, 23, 45))}?edition=roman_1960`)
    expect(screen.getByText('Tuesday, December 8, 2026')).toBeInTheDocument()
  }, 30000)
})
