import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { DivineOfficePage } from '../pages/DivineOfficePage'
import { OFFICE_HOURS, isValidIsoDate, shiftDate, today } from '../lib/divineOffice'
import type { Office, OfficeLineKind } from '../types/divineOffice'

// Every word below is neutral filler for the tests, never a real liturgical text.
const line = (kind: OfficeLineKind, text: string, label: string | null = null) => ({ kind, text, label })
const office = (date: string): Office => ({
  date, hour: 'compline', hour_name: 'Compline', hour_latin: 'Completorium', liturgical_day: 'Filler Feast Duplex ~ III. classis', liturgical_day_detail: null,
  rank: 'III. classis', season: 'Lent', season_code: 'Quad2',
  sections: [
    { id: 's1', heading_latin: 'Incipit', heading_english: 'Start', note_latin: null, note_english: null, rows: [{ aligned: true, marks: [], latin: [line('versicle', 'Latin versicle filler', '℣.'), line('response', 'Latin response filler', '℟.')], english: [line('versicle', 'English versicle filler', '℣.'), line('response', 'English response filler', '℟.')] }] },
    { id: 's2', heading_latin: 'Psalmi', heading_english: 'Psalms', note_latin: '{ex Psalterio}', note_english: '{from the Psalter}', rows: [{ aligned: true, marks: [], latin: [line('antiphon', 'Latin antiphon filler', 'Ant.'), line('psalm_verse', 'Latin verse filler', '4:2')], english: [line('antiphon', 'English antiphon filler', 'Ant.'), line('psalm_verse', 'English verse filler', '4:2')] }] },
  ],
  source: { name: 'Divinum Officium', url: 'https://github.com/DivinumOfficium/divinum-officium', commit: 'abcdef0123456789abcdef0123456789abcdef01', version: 'Rubrics 1960 - 1960', code_license: 'MIT (repository LICENSE)', texts: 'Texts as supplied; per-translation rights are not verified here.' },
})
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
let requests: string[] = []

function stub(respond: (path: string) => Response | Promise<Response> = path => json(office(path.split('/')[2]))) {
  requests = []
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    const path = input.replace('/api', '')
    requests.push(path)
    if (path === '/divine-office/saved') return json([])
    return respond(path)
  }))
}
function open(url = '/divine-office') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}><Routes><Route path="/divine-office" element={<DivineOfficePage />} /><Route path="/devotions" element={<p>The Oratory</p>} /></Routes></MemoryRouter></QueryClientProvider>)
}
const bodies = () => [...document.querySelectorAll<HTMLElement>('.office-line')].map(element => [element.getAttribute('lang'), element.textContent])

beforeEach(() => { window.localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

describe('the hours', () => {
  it('lists all eight canonical hours, in order, every one enabled', async () => {
    stub()
    open('/divine-office?date=2026-11-10&hour=compline')
    const group = within(await screen.findByRole('group', { name: 'Hour' }))
    expect(group.getAllByRole('button').map(button => button.textContent)).toEqual(OFFICE_HOURS.map(hour => `${hour.name}${hour.latin}`))
    expect(group.getAllByRole('button')).toHaveLength(8)
    expect(OFFICE_HOURS.map(hour => hour.slug)).toEqual(['matins', 'lauds', 'prime', 'terce', 'sext', 'none', 'vespers', 'compline'])
    for (const button of group.getAllByRole('button')) expect(button).toBeEnabled()
    expect(document.body.textContent).not.toMatch(/forthcoming/i)
  })

  it('asks the server for the chosen hour and date and keeps the date when the hour changes', async () => {
    stub(path => json({ ...office(path.split('/')[2]), hour: path.split('/')[3] }))
    open('/divine-office?date=2026-11-10&hour=compline')
    await screen.findByRole('heading', { name: /Filler Feast/ })
    for (const [name, slug] of [['Matins', 'matins'], ['Lauds', 'lauds'], ['Prime', 'prime'], ['Terce', 'terce'], ['Sext', 'sext'], ['None', 'none'], ['Vespers', 'vespers']]) {
      await userEvent.click(within(screen.getByRole('group', { name: 'Hour' })).getByRole('button', { name: new RegExp(`^${name}`) }))
      await screen.findByRole('heading', { name: /Filler Feast/ })
      expect(requests.at(-1)).toBe(`/divine-office/2026-11-10/${slug}`)
    }
    expect(screen.getByLabelText('Office date')).toHaveValue('2026-11-10')
  })

  it('shows an hour the server says is not available as an error, never as prayer text', async () => {
    stub(() => json({ detail: 'Vespers is not available.' }, 501))
    open('/divine-office?date=2026-11-10&hour=vespers')
    expect(await screen.findByRole('alert')).toHaveTextContent('Vespers is not available.')
    expect(document.querySelectorAll('.office-line')).toHaveLength(0)
  })
})

describe('the date', () => {
  it('defaults to today and asks for Compline of that date', async () => {
    stub()
    open()
    await screen.findByRole('heading', { name: /Filler Feast/ })
    expect(requests.filter(path => path !== '/divine-office/saved')).toEqual([`/divine-office/${today()}/compline`])
    expect(screen.getByLabelText('Office date')).toHaveValue(today())
  })

  it('moves a day at a time and returns to today', async () => {
    stub()
    open('/divine-office?date=2026-03-01&hour=compline')
    await screen.findByRole('heading', { name: /Filler Feast/ })
    await userEvent.click(screen.getByRole('button', { name: 'Next day' }))
    await userEvent.click(screen.getByRole('button', { name: 'Previous day' }))
    await userEvent.click(screen.getByRole('button', { name: 'Previous day' }))
    expect(requests).toContain('/divine-office/2026-03-02/compline')
    expect(requests.at(-1)).toBe('/divine-office/2026-02-28/compline')
    expect(screen.getByLabelText('Office date')).toHaveValue('2026-02-28')
    await userEvent.click(screen.getByRole('button', { name: 'Today' }))
    expect(screen.getByLabelText('Office date')).toHaveValue(today())
  })

  it('treats a nonsense date as today and validates dates properly', () => {
    expect(isValidIsoDate('2026-02-30')).toBe(false)
    expect(isValidIsoDate('2026-13-01')).toBe(false)
    expect(isValidIsoDate('2026-03-04')).toBe(true)
    expect(shiftDate('2026-12-31', 1)).toBe('2027-01-01')
    expect(shiftDate('2028-03-01', -1)).toBe('2028-02-29')
  })
})

describe('reading', () => {
  it('shows the liturgical day, season, rank and the Office in English by default with each part headed', async () => {
    stub()
    open('/divine-office?date=2026-03-04&hour=compline')
    expect(await screen.findByRole('heading', { name: 'Filler Feast Duplex ~ III. classis' })).toBeInTheDocument()
    expect(screen.getByText('Lent · III. classis')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 2 }).map(heading => heading.textContent)).toEqual(['Filler Feast Duplex ~ III. classis', 'Start', 'Psalms'])
    expect(bodies().every(([language]) => language === 'en')).toBe(true)
  })

  it('switches to Latin and to side by side, Latin first, remembering the choice', async () => {
    stub()
    open('/divine-office?date=2026-03-04&hour=compline')
    await screen.findByRole('heading', { name: 'Start' })
    await userEvent.click(screen.getByRole('button', { name: 'Latin' }))
    expect(bodies().every(([language]) => language === 'la')).toBe(true)
    expect(screen.getByRole('heading', { name: 'Incipit' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Side by side' }))
    expect(bodies().slice(0, 4).map(([language]) => language)).toEqual(['la', 'la', 'en', 'en'])
    expect(screen.getByRole('heading', { name: 'Incipit · Start' })).toBeInTheDocument()
    expect(document.querySelectorAll('.office-pair')).toHaveLength(2)
    expect(window.localStorage.getItem('optima-pars:office-view')).toBe('both')
  })

  it('keeps versicles and responses on their own lines and psalm verses numbered', async () => {
    stub()
    open('/divine-office?date=2026-03-04&hour=compline')
    await screen.findByRole('heading', { name: 'Start' })
    const versicle = screen.getByText('English versicle filler').closest('p')!
    const response = screen.getByText('English response filler').closest('p')!
    expect(versicle).not.toBe(response)
    expect(versicle.textContent).toBe('℣. English versicle filler')
    expect(response.className).toContain('is-response')
    expect(screen.getByText('English verse filler').closest('p')!.textContent).toBe('4:2 English verse filler')
  })

  it('names its source, version and licence, and says translation rights are not verified', async () => {
    stub()
    open('/divine-office?date=2026-03-04&hour=compline')
    const footer = await screen.findByText(/Source\./)
    expect(footer.closest('footer')).toHaveTextContent('Rubrics 1960 - 1960')
    expect(footer.closest('footer')).toHaveTextContent('commit abcdef0123')
    expect(footer.closest('footer')).toHaveTextContent('MIT')
    expect(screen.getByText(/rights are not verified/)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/approv|publish|editorial/i)
  })
})

describe('when the Office cannot be produced', () => {
  it('says it is unavailable and shows no prayer text at all', async () => {
    stub(() => json({ detail: 'The Divine Office is unavailable: The Divinum Officium engine is not configured (set DIVINUM_OFFICIUM_PATH to a checkout).' }, 503))
    open('/divine-office?date=2026-03-04&hour=compline')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The Divine Office is unavailable.')
    expect(alert).toHaveTextContent('not configured')
    expect(alert).toHaveTextContent('Nothing is shown in its place')
    expect(document.querySelectorAll('.office-line')).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('reports any other failure plainly and invents nothing', async () => {
    stub(() => json({ detail: 'boom' }, 502))
    open('/divine-office?date=2026-03-04&hour=compline')
    expect(await screen.findByRole('alert')).toHaveTextContent('The Office could not be loaded.')
    expect(document.querySelectorAll('.office-line')).toHaveLength(0)
  })
})

// ---- Long hours: Matins with three nocturns ----------------------------------------------------------------------
const mark = (kind: string, line: number, latin: string, english: string) => ({ line, kind, latin, english })
const matins = (date: string): Office => ({
  ...office(date), hour: 'matins', hour_name: 'Matins', hour_latin: 'Matutinum',
  sections: [
    { id: 's1', heading_latin: 'Incipit', heading_english: 'Start', note_latin: null, note_english: null, rows: [{ aligned: true, marks: [], latin: [line('versicle', 'Latin start filler', '℣.')], english: [line('versicle', 'English start filler', '℣.')] }] },
    {
      id: 's2', heading_latin: 'Psalmi cum lectionibus', heading_english: 'Psalms with readings', note_latin: '{nota latina}', note_english: '{english note}',
      rows: [
        { aligned: true, marks: [mark('nocturn', 0, 'Nocturnus I', 'Nocturn I')], latin: [line('rubric', 'Nocturnus I'), line('antiphon', 'Latin antiphon one', 'Ant.')], english: [line('rubric', 'Nocturn I'), line('antiphon', 'English antiphon one', 'Ant.')] },
        { aligned: true, marks: [mark('nocturn', 0, 'Nocturnus II', 'Nocturn II')], latin: [line('rubric', 'Nocturnus II'), line('text', 'Latin lesson four')], english: [line('rubric', 'Nocturn II'), line('text', 'English lesson four')] },
        { aligned: false, marks: [mark('nocturn', 0, 'Nocturnus III', 'Nocturn III'), mark('te_deum', 2, 'Te Deum', 'Te Deum')], latin: [line('rubric', 'Nocturnus III'), line('text', 'Latin lesson seven'), line('rubric', 'Te Deum')], english: [line('rubric', 'Nocturn III'), line('text', 'English lesson seven part one'), line('text', 'part two'), line('rubric', 'Te Deum')] },
      ],
    },
    {
      id: 's3', heading_latin: 'Oratio', heading_english: 'Prayer', note_latin: null, note_english: null,
      rows: [{ aligned: true, marks: [mark('commemoration', 1, 'Commemoratio S. Filler', 'Commemoration of St Filler')], latin: [line('text', 'Latin prayer filler'), line('rubric', 'Commemoratio S. Filler')], english: [line('text', 'English prayer filler'), line('rubric', 'Commemoration of St Filler')] }],
    },
  ],
})
const stubMatins = () => stub(path => json(matins(path.split('/')[2])))

describe('a long hour (Matins)', () => {
  it('offers a contents with every part and its nocturns, Te Deum and commemorations, linking to each', async () => {
    stubMatins()
    open('/divine-office?date=2026-12-25&hour=matins')
    const toc = within(await screen.findByRole('navigation', { name: 'Contents' }))
    expect(toc.getAllByRole('link').map(link => link.textContent)).toEqual(['Start', 'Psalms with readings', 'Nocturn I', 'Nocturn II', 'Nocturn III', 'Te Deum', 'Prayer', 'Commemoration of St Filler'])
    for (const link of toc.getAllByRole('link')) expect(document.getElementById(link.getAttribute('href')!.slice(1)), link.textContent ?? '').not.toBeNull()
    expect(screen.getByText('Contents').closest('details')).toHaveAttribute('open')
  })

  it('makes each nocturn a clear heading and keeps the Latin and English of a row side by side', async () => {
    stubMatins()
    open('/divine-office?date=2026-12-25&hour=matins')
    await screen.findByRole('heading', { name: 'Psalms with readings' })
    await userEvent.click(screen.getByRole('button', { name: 'Side by side' }))
    expect([...document.querySelectorAll('h3.office-nocturn')].map(heading => [heading.getAttribute('lang'), heading.textContent])).toEqual([['la', 'Nocturnus I'], ['en', 'Nocturn I'], ['la', 'Nocturnus II'], ['en', 'Nocturn II'], ['la', 'Nocturnus III'], ['en', 'Nocturn III']])
    const pairs = [...document.querySelectorAll('.office-pair')]
    expect(pairs).toHaveLength(5)
    for (const pair of pairs) expect([...pair.children].map(column => column.getAttribute('lang'))).toEqual(['la', 'en'])
    expect(pairs[0].textContent).toContain('Latin start filler')
    expect(pairs[0].textContent).toContain('English start filler')
    expect(pairs[4].textContent).toContain('Latin prayer filler')
    expect(document.querySelector('.office-pair.is-unaligned')?.textContent).toContain('English lesson seven part one')      // the engine's non-parallel row is shown whole, not trimmed
  })

  it('shows the notes of both languages side by side and never drops a part or repeats one', async () => {
    stubMatins()
    open('/divine-office?date=2026-12-25&hour=matins')
    await screen.findByRole('heading', { name: 'Psalms with readings' })
    await userEvent.click(screen.getByRole('button', { name: 'Side by side' }))
    expect(screen.getByText('{nota latina} · {english note}')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 2 }).map(heading => heading.textContent)).toEqual(['Filler Feast Duplex ~ III. classis', 'Incipit · Start', 'Psalmi cum lectionibus · Psalms with readings', 'Oratio · Prayer'])
    for (const text of ['Latin lesson four', 'English lesson four', 'Latin lesson seven', 'English lesson seven part one', 'part two', 'Latin prayer filler', 'English prayer filler']) expect(screen.getAllByText(text)).toHaveLength(1)
    expect(document.querySelectorAll('[id]').length).toBe(new Set([...document.querySelectorAll('[id]')].map(element => element.id)).size)      // no duplicate anchors
  })

  it('shows one language at a time with that language’s contents and notes', async () => {
    stubMatins()
    open('/divine-office?date=2026-12-25&hour=matins')
    await screen.findByRole('heading', { name: 'Psalms with readings' })
    await userEvent.click(screen.getByRole('button', { name: 'Latin' }))
    const toc = within(screen.getByRole('navigation', { name: 'Contents' }))
    expect(toc.getAllByRole('link').map(link => link.textContent)).toEqual(['Incipit', 'Psalmi cum lectionibus', 'Nocturnus I', 'Nocturnus II', 'Nocturnus III', 'Te Deum', 'Oratio', 'Commemoratio S. Filler'])
    expect(screen.getByText('{nota latina}')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('English lesson')
    expect(document.querySelectorAll('h3.office-nocturn')).toHaveLength(3)
  })
})

describe('regression: Compline is unchanged', () => {
  it('still renders the Compline fixture exactly as before with its contents', async () => {
    stub()
    open('/divine-office?date=2026-03-04&hour=compline')
    await screen.findByRole('heading', { name: 'Start' })
    expect(screen.getAllByRole('heading', { level: 2 }).map(heading => heading.textContent)).toEqual(['Filler Feast Duplex ~ III. classis', 'Start', 'Psalms'])
    expect(screen.getByRole('navigation', { name: 'Contents' })).toBeInTheDocument()
    expect(document.querySelector('.office-hour-title')?.textContent).toBe('Compline (Completorium)')
    expect(screen.getByText('English verse filler').closest('p')?.textContent).toBe('4:2 English verse filler')
  })
})
