import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { LiturgicalCalendarCard } from '../components/today/LiturgicalCalendarCard'
import { isoDate } from '../lib/divineOffice'
import type { CalendarDay } from '../types/liturgicalCalendar'

// Neutral fixtures shaped like the server's answer; the real celebrations and descriptions come from the engine, never from the front end.
const engine = { name: 'Divinum Officium', url: 'https://github.com/DivinumOfficium/divinum-officium', commit: 'abcdef0123456789abcdef0123456789abcdef01', version: 'Rubrics 1960 - 1960' }
const saint: CalendarDay = {
  date: '2026-11-10', edition: 'roman_1960', celebration: 'St. Filler Example', celebration_latin: 'S. Fillerii Confessoris', celebration_source: 'upstream_english', designation: null, celebration_type: 'saint', type_label: 'Saint', qualifier: 'Confessor',
  rank: 'III. classis', rank_class: 'III', rank_label: 'Confessor, III Class', season: 'Time after Pentecost', season_code: 'Pent23',
  commemorations: [{ latin: 'Commemoratio S. Alii', english: 'Commemoration of St. Another' }, { latin: 'Commemoratio S. Tertii', english: null }],
  description: { text: 'Filler was born in a small town. He studied and was ordained. He served the poor.', source: { name: 'The Roman Breviary, Matins lesson (English), as supplied by Divinum Officium', reference: 'Matins, Reading 3, St. Filler Example (Sancti/11-10.txt); the lesson’s opening sentences, verbatim', note: 'Translation rights are not verified' } },
  engine,
}
const feast: CalendarDay = { ...saint, celebration: 'Filler Feast of Our Lady', celebration_type: 'feast', qualifier: null, rank: 'I. classis', rank_class: 'I', rank_label: 'I Class', commemorations: [], description: null, season: 'Lent' }
const sunday: CalendarDay = { ...feast, celebration: 'Fifth Filler Sunday after Epiphany', celebration_latin: 'Dominica V Post Epiphaniam III. Novembris', celebration_source: 'translated', designation: 'Third Sunday of November (Breviary numbering)', celebration_type: 'sunday', rank_label: 'II Class' }
const untranslated: CalendarDay = { ...feast, celebration: 'In Dedicatione Filleriana', celebration_latin: 'In Dedicatione Filleriana', celebration_source: 'latin_untranslated', rank_label: 'III Class' }

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
let requests: string[]

function mount(answer: () => Response | Promise<Response>) {
  requests = []
  vi.stubGlobal('fetch', vi.fn(async (input: string) => { requests.push(input.replace('/api', '')); return answer() }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><LiturgicalCalendarCard /></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(2026, 10, 10, 12, 0)) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('the Traditional Liturgical Calendar card', () => {
  it('shows the saint, rank, description, commemoration and a link to the same day’s Divine Office', async () => {
    mount(() => json(saint))
    expect(await screen.findByRole('heading', { name: 'St. Filler Example' })).toBeInTheDocument()
    expect(screen.getByText('Traditional Liturgical Calendar')).toBeInTheDocument()
    expect(screen.getByText('Tuesday, November 10, 2026')).toBeInTheDocument()
    expect(screen.getByText('Confessor, III Class')).toBeInTheDocument()
    expect(screen.getByText('Time after Pentecost')).toBeInTheDocument()
    expect(screen.getByText('Filler was born in a small town. He studied and was ordained. He served the poor.')).toBeInTheDocument()
    expect(screen.getByText(/Commemorated:/).closest('p')?.textContent).toBe('Commemorated: Commemoration of St. Another; Commemoratio S. Tertii')     // English where the engine gives it, Latin otherwise
    expect(screen.getByRole('link', { name: /Read Today’s Divine Office/ })).toHaveAttribute('href', '/divine-office?date=2026-11-10')
    expect(requests).toEqual(['/liturgical-calendar/2026-11-10?edition=roman_1960'])
  })

  it('keeps the source attribution with the description', async () => {
    mount(() => json(saint))
    const source = await screen.findByText(/^Source: The Roman Breviary/)
    expect(source).toHaveAttribute('title', expect.stringContaining('Sancti/11-10.txt'))
    expect(source).toHaveAttribute('title', expect.stringContaining('verbatim'))
  })

  it('shows a feast or Sunday with its rank and no description, source line or invented text', async () => {
    mount(() => json(feast))
    expect(await screen.findByRole('heading', { name: 'Filler Feast of Our Lady' })).toBeInTheDocument()
    expect(screen.getByText('I Class')).toBeInTheDocument()
    expect(document.querySelector('.calendar-description')).toBeNull()
    expect(screen.queryByText(/Source:/)).toBeNull()
    expect(screen.queryByText(/Commemorated/)).toBeNull()
    expect(screen.getByRole('link', { name: /Read Today’s Divine Office/ })).toBeInTheDocument()
  })

  it('shows an English name with the original Latin title beneath it, in smaller Latin-language text', async () => {
    mount(() => json(sunday))
    const heading = await screen.findByRole('heading', { name: 'Fifth Filler Sunday after Epiphany' })
    expect(heading).toHaveAttribute('lang', 'en')
    const latin = screen.getByText('Dominica V Post Epiphaniam III. Novembris')
    expect(latin).toHaveAttribute('lang', 'la')
    expect(latin.className).toBe('calendar-latin')
    expect(screen.getByText('Third Sunday of November (Breviary numbering)')).toBeInTheDocument()            // the Breviary's own count, labelled as such, not a civil date
    expect(screen.getByText('II Class')).toBeInTheDocument()
  })

  it('shows the Saint’s original Latin title too, and a feast with the rank beneath its name', async () => {
    mount(() => json(saint))
    await screen.findByRole('heading', { name: 'St. Filler Example' })
    expect(screen.getByText('S. Fillerii Confessoris')).toHaveAttribute('lang', 'la')
    const order = [...document.querySelectorAll('.calendar-card h2, .calendar-rank, .calendar-latin, .calendar-season, .calendar-description')].map(element => element.className || element.tagName)
    expect(order).toEqual(['calendar-celebration', 'calendar-rank', 'calendar-latin', 'calendar-season', 'calendar-description'])
  })

  it('keeps an untranslated title as the Latin heading, once, marked Latin, never as English', async () => {
    mount(() => json(untranslated))
    const heading = await screen.findByRole('heading', { name: 'In Dedicatione Filleriana' })
    expect(heading).toHaveAttribute('lang', 'la')
    expect(screen.getAllByText('In Dedicatione Filleriana')).toHaveLength(1)                                  // not repeated as a secondary line
    expect(document.querySelector('.calendar-latin')).toBeNull()
  })

  it('uses the reader’s local date, not UTC, including late in the evening and just after midnight', async () => {
    vi.setSystemTime(new Date(2026, 10, 10, 23, 45))
    const late = mount(() => json(saint))
    await screen.findByRole('heading', { name: 'St. Filler Example' })
    expect(requests[0]).toBe(`/liturgical-calendar/${isoDate(new Date(2026, 10, 10, 23, 45))}?edition=roman_1960`)
    expect(requests[0]).toContain('2026-11-10')                                                                // still the 10th for the reader, whatever UTC says
    late.unmount()
    vi.setSystemTime(new Date(2026, 10, 11, 0, 5))
    mount(() => json(saint))
    await screen.findByRole('heading', { name: 'St. Filler Example' })
    expect(requests[0]).toContain('2026-11-11')
    expect(screen.getByRole('link', { name: /Read Today’s Divine Office/ })).toHaveAttribute('href', '/divine-office?date=2026-11-11')
  })

  it('says plainly when the calendar is unavailable, shows nothing in its place and offers no link', async () => {
    mount(() => json({ detail: 'The liturgical calendar is unavailable: not configured' }, 503))
    expect(await screen.findByText(/The traditional calendar is unavailable right now/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull()
    expect(screen.queryByRole('link')).toBeNull()
    expect(document.body.textContent).not.toMatch(/St\.|Feast|Confessor/)
  })

  it('shows a quiet message while the day is being looked up', async () => {
    mount(() => new Promise<Response>(() => {}))
    expect(await screen.findByText('Looking up the day…')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/approv|publish|editorial/i)
  })

  it('records an exact correction of upstream’s English title on the heading, keeping the Latin beneath it', async () => {
    mount(() => json({ ...saint, celebration: 'St. Justin Martyr', celebration_latin: 'S. Justini Martyris', english_correction: 'Upstream’s English title “St. Justini Martyr” was corrected to “St. Justin Martyr”' }))
    const heading = await screen.findByRole('heading', { name: 'St. Justin Martyr' })
    expect(heading).toHaveAttribute('title', expect.stringContaining('St. Justini Martyr'))
    expect(screen.getByText('S. Justini Martyris')).toHaveAttribute('lang', 'la')
    expect(screen.queryByText('St. Justini Martyr')).toBeNull()                                              // the mixed-language form is never shown
  })

  it('has no title attribute when nothing was corrected', async () => {
    mount(() => json(saint))
    expect(await screen.findByRole('heading', { name: 'St. Filler Example' })).not.toHaveAttribute('title')
  })
})
