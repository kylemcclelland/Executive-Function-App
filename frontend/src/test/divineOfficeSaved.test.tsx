import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { DevotionBrief } from '../types/devotions'
import type { Office, OfficeLine, OfficeLineKind, OfficeUnit, SavedOfficeBrief, SavedOfficeDetail } from '../types/divineOffice'

// Every word below is neutral filler for the tests, never a real liturgical text.
const line = (kind: OfficeLineKind, text: string, label: string | null = null): OfficeLine => ({ kind, text, label })
const unit = (id: string, kind: string, title_latin: string, title_english: string, start: number, end: number, date_specific = false): OfficeUnit => ({ id, kind, title_latin, title_english, start, end, date_specific })
const source = { name: 'Divinum Officium', url: 'https://github.com/DivinumOfficium/divinum-officium', commit: 'abcdef0123456789abcdef0123456789abcdef01', version: 'Rubrics 1960 - 1960', code_license: 'MIT (repository LICENSE)', texts: 'Texts as supplied; per-translation rights are not verified here.' }
const PSALM = 'psalm:0123456789abcdef'
const ANTIPHON = 'antiphon:2026-11-10:compline:0123456789abcdef'
const HYMN = 'hymn:fedcba9876543210'

const office: Office = {
  date: '2026-11-10', hour: 'compline', hour_name: 'Compline', hour_latin: 'Completorium', liturgical_day: 'Filler Feast', liturgical_day_detail: null, rank: 'III. classis', season: 'Lent', season_code: 'Quad2',
  source,
  sections: [
    {
      id: 's1', heading_latin: 'Psalmi', heading_english: 'Psalms', note_latin: null, note_english: null,
      rows: [{
        aligned: true, marks: [], units: [unit(ANTIPHON, 'antiphon', 'Antiphona ad Psalmus 4', 'Antiphon to Psalm 4', 0, 1, true), unit(PSALM, 'psalm', 'Psalmus 4', 'Psalm 4', 1, 3)],
        latin: [line('antiphon', 'Latin antiphon filler', 'Ant.'), line('psalm_heading', '[1]', 'Psalmus 4'), line('psalm_verse', 'Latin verse filler', '4:2'), line('versicle', 'Latin gloria filler', '℣.')],
        english: [line('antiphon', 'English antiphon filler', 'Ant.'), line('psalm_heading', '[1]', 'Psalm 4'), line('psalm_verse', 'English verse filler', '4:2'), line('versicle', 'English gloria filler', '℣.')],
      }],
    },
    {
      id: 's2', heading_latin: 'Capitulum Responsorium Versus', heading_english: 'Chapter Responsory Verse', note_latin: null, note_english: null,
      rows: [{ aligned: true, marks: [], units: [], latin: [line('text', 'Latin chapter filler')], english: [line('text', 'English chapter filler')] }],      // a chapter: no Save button
    },
    {
      id: 's3', heading_latin: 'Hymnus', heading_english: 'Hymn', note_latin: null, note_english: null,
      rows: [{ aligned: true, marks: [], units: [unit(HYMN, 'hymn', 'Hymnus: Latin stanza one', 'Hymn: English stanza one', 0, 2)], latin: [line('text', 'Latin stanza one'), line('text', 'Latin stanza two')], english: [line('text', 'English stanza one'), line('text', 'English stanza two')] }],
    },
  ],
}

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
let saved: SavedOfficeBrief[]
let calls: { path: string; method: string; body?: unknown }[]
let savedStatus = 200

const item = (id: string, unit_key: string, kind: string, title_english: string, extra: Partial<SavedOfficeBrief> = {}): SavedOfficeBrief => ({ id, unit_key, kind, title_latin: `Latin ${title_english}`, title_english, date_specific: false, source_hour: 'compline', source_hour_name: 'Compline', source_date: '2026-11-10', ...extra })
const brief = (id: string, title: string, bookmarked: boolean): DevotionBrief => ({ id, slug: id, title, subtitle: null, category: null, estimated_minutes: null, bookmarked, has_text: true })

function stub(devotions: DevotionBrief[] = [], detail?: SavedOfficeDetail | number) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = input.replace('/api', '')
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(String(options.body)) : undefined
    calls.push({ path, method, body })
    if (path === '/divine-office/saved' && method === 'GET') return savedStatus === 200 ? json(saved) : json({ detail: 'boom' }, savedStatus)
    if (path === '/divine-office/saved' && method === 'POST') {
      const created = item(`new-${saved.length}`, body.unit_id, body.unit_id.split(':')[0], 'Saved now', { date_specific: body.unit_id.startsWith('antiphon') })
      saved = [...saved, created]
      return json({ saved: true, item: created }, 201)
    }
    if (path.startsWith('/divine-office/saved/')) {
      if (method === 'DELETE') { saved = saved.filter(entry => `/divine-office/saved/${entry.id}` !== path); return json({ saved: false }) }
      return typeof detail === 'number' ? json({ detail: 'Saved prayer not found' }, detail) : json(detail)
    }
    if (path.startsWith('/divine-office/')) return json(office)
    if (path === '/devotions') return json(devotions)
    return json({ detail: 'unexpected' }, 404)
  }))
}

function open(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
}
const reader = () => open('/divine-office?date=2026-11-10&hour=compline')
const buttons = () => screen.queryAllByRole('button', { name: /Saved Prayers:/ })

beforeEach(() => { window.localStorage.clear(); saved = []; savedStatus = 200 })
afterEach(() => { vi.unstubAllGlobals() })

describe('saving from the Office', () => {
  it('offers a Save control only beside a reliably identified prayer, never beside a chapter', async () => {
    stub()
    reader()
    await screen.findByRole('heading', { name: 'Psalms' })
    expect(await screen.findAllByRole('button', { name: /Save to Saved Prayers/ })).toHaveLength(3)
    expect(buttons().map(button => button.getAttribute('aria-label'))).toEqual(['Save to Saved Prayers: Antiphon to Psalm 4 (this day)', 'Save to Saved Prayers: Psalm 4', 'Save to Saved Prayers: Hymn: English stanza one'])
    const chapter = screen.getByText('English chapter filler').closest('.office-section')!
    expect(within(chapter as HTMLElement).queryAllByRole('button')).toHaveLength(0)
  })

  it('saves a psalm sending only a reference, then shows it saved without leaving the page', async () => {
    stub()
    reader()
    await userEvent.click(await screen.findByRole('button', { name: 'Save to Saved Prayers: Psalm 4' }))
    const post = calls.find(call => call.method === 'POST')!
    expect(post).toEqual({ path: '/divine-office/saved', method: 'POST', body: { date: '2026-11-10', hour: 'compline', unit_id: PSALM } })     // no prayer text is sent
    expect(await screen.findByRole('button', { name: /Remove from Saved Prayers: Psalm 4/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('English verse filler')).toBeInTheDocument()
  })

  it('saves a date-specific antiphon and a hymn, and unsaves with a second click', async () => {
    stub()
    reader()
    await userEvent.click(await screen.findByRole('button', { name: /Save to Saved Prayers: Antiphon to Psalm 4/ }))
    await userEvent.click(screen.getByRole('button', { name: /Save to Saved Prayers: Hymn/ }))
    await waitFor(() => expect(saved.map(entry => entry.unit_key)).toEqual([ANTIPHON, HYMN]))
    await userEvent.click(await screen.findByRole('button', { name: /Remove from Saved Prayers: Hymn/ }))
    expect(calls.find(call => call.method === 'DELETE')).toMatchObject({ path: '/divine-office/saved/new-1' })
    await waitFor(() => expect(saved.map(entry => entry.unit_key)).toEqual([ANTIPHON]))
    expect(await screen.findByRole('button', { name: /Save to Saved Prayers: Hymn/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows what is already saved as saved, on reopening the Office', async () => {
    saved = [item('s1', PSALM, 'psalm', 'Psalm 4')]
    stub()
    reader()
    expect(await screen.findByRole('button', { name: /Remove from Saved Prayers: Psalm 4/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /Save to Saved Prayers: Hymn/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('keeps one control per prayer in English, Latin and side-by-side views', async () => {
    stub()
    reader()
    await screen.findByRole('button', { name: 'Save to Saved Prayers: Psalm 4' })
    for (const view of ['Latin', 'Side by side', 'English']) {
      await userEvent.click(screen.getByRole('button', { name: view }))
      expect(buttons()).toHaveLength(3)
    }
    await userEvent.click(screen.getByRole('button', { name: 'Latin' }))
    expect(screen.getByRole('button', { name: 'Save to Saved Prayers: Psalmus 4' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Side by side' }))
    const pair = document.querySelector('.office-pair')!
    expect(pair.querySelectorAll('.office-save')).toHaveLength(2)                                                   // the antiphon and the psalm of this row, once each
    expect(pair.querySelectorAll('.office-column[lang="la"] .office-save')).toHaveLength(2)
    expect(pair.querySelectorAll('.office-column[lang="en"] .office-save')).toHaveLength(0)                       // not duplicated into the English column
  })

  it('offers no Save control, and says so, when saving is not available', async () => {
    savedStatus = 500
    stub()
    reader()
    await screen.findByRole('heading', { name: 'Psalms' })
    expect(await screen.findByText('Saving prayers is not available on this server.')).toBeInTheDocument()
    expect(buttons()).toHaveLength(0)
    expect(screen.getByText('English verse filler')).toBeInTheDocument()                                              // the Office itself still reads
  })

  it('does not change how the text is shown', async () => {
    stub()
    reader()
    await screen.findByRole('button', { name: 'Save to Saved Prayers: Psalm 4' })
    expect(screen.getByText('English verse filler').closest('p')!.textContent).toBe('4:2 English verse filler')
    expect(document.body.textContent).not.toMatch(/approv|publish|editorial/i)
  })
})

describe('Saved Prayers in The Oratory', () => {
  it('lists saved Office prayers beside the saved devotions, each with its hour and date', async () => {
    saved = [item('s1', PSALM, 'psalm', 'Psalm 4'), item('s2', ANTIPHON, 'antiphon', 'Antiphon to Psalm 4', { date_specific: true, source_hour: 'vespers', source_hour_name: 'Vespers', source_date: '2026-03-04' })]
    stub([brief('alpha', 'Filler Alpha', true), brief('beta', 'Filler Beta', false)])
    open('/devotions')
    const region = within(await screen.findByRole('heading', { name: 'Saved prayers' }).then(heading => heading.closest('section')!))
    expect((await region.findAllByRole('link')).map(link => link.getAttribute('href'))).toEqual(['/devotions/alpha', '/divine-office/saved/s1', '/divine-office/saved/s2'])
    expect(region.getByRole('link', { name: /Filler Alpha/ })).toBeInTheDocument()
    expect(region.queryByText('Filler Beta')).toBeNull()                                                              // an unsaved devotion is not listed
    expect(region.getByText(/Divine Office · Compline · Tuesday, November 10, 2026/)).toBeInTheDocument()
    expect(region.getByText(/Divine Office · Vespers · Wednesday, March 4, 2026/)).toBeInTheDocument()
    expect(region.getByText('Antiphon')).toBeInTheDocument()
  })

  it('shows the existing empty note only when nothing at all is saved, and keeps devotions working without Office items', async () => {
    stub([brief('alpha', 'Filler Alpha', false)])
    open('/devotions')
    expect(await screen.findByText('Nothing saved yet')).toBeInTheDocument()
    vi.unstubAllGlobals()
    stub([brief('alpha', 'Filler Alpha', true)])
    document.body.innerHTML = ''
    open('/devotions')
    const section = await screen.findByRole('heading', { name: 'Saved prayers' }).then(heading => heading.closest('section')!)
    expect(await within(section).findByRole('link', { name: /Filler Alpha/ })).toBeInTheDocument()
    expect(within(section).queryByText('Nothing saved yet')).toBeNull()
  })

  it('still lists saved devotions when the saved Office prayers cannot be loaded', async () => {
    savedStatus = 500
    stub([brief('alpha', 'Filler Alpha', true)])
    open('/devotions')
    const section = await screen.findByRole('heading', { name: 'Saved prayers' }).then(heading => heading.closest('section')!)
    expect(await within(section).findByRole('link', { name: /Filler Alpha/ })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('reopening a saved prayer', () => {
  const detail: SavedOfficeDetail = {
    ...item('s1', PSALM, 'psalm', 'Psalm 4'), source,
    latin: [line('psalm_heading', '[1]', 'Psalmus 4'), line('psalm_verse', 'Latin verse filler', '4:2')],
    english: [line('psalm_heading', '[1]', 'Psalm 4'), line('psalm_verse', 'English verse filler', '4:2')],
  }

  it('shows the saved wording exactly, with its source, hour and date, in the chosen language', async () => {
    saved = [item('s1', PSALM, 'psalm', 'Psalm 4')]
    stub([], detail)
    open('/divine-office/saved/s1')
    expect(await screen.findByRole('heading', { name: 'Psalm 4' })).toBeInTheDocument()
    expect(screen.getByText(/Psalm · Divine Office · Compline · Tuesday, November 10, 2026 \(first saved from this hour\)/)).toBeInTheDocument()
    expect(screen.getByText('English verse filler').closest('p')!.textContent).toBe('4:2 English verse filler')
    expect(screen.queryByText('Latin verse filler')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Latin' }))
    expect(screen.getByText('Latin verse filler')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Side by side' }))
    expect(document.querySelectorAll('.office-pair .office-column')).toHaveLength(2)
    expect(screen.getByRole('link', { name: 'Open this hour in the Office' })).toHaveAttribute('href', '/divine-office?date=2026-11-10&hour=compline')
    expect(document.querySelector('.office-source')).toHaveTextContent('Rubrics 1960 - 1960')
    expect(document.querySelector('.office-source')).toHaveTextContent('rights are not verified')
  })

  it('says a date-specific prayer belongs to its day', async () => {
    stub([], { ...detail, ...item('s2', ANTIPHON, 'antiphon', 'Antiphon to Psalm 4', { date_specific: true }) })
    open('/divine-office/saved/s2')
    expect(await screen.findByText(/Antiphon · Divine Office · Compline · Tuesday, November 10, 2026 \(belongs to this day\)/)).toBeInTheDocument()
  })

  it('removes it from Saved Prayers and returns to The Oratory', async () => {
    saved = [item('s1', PSALM, 'psalm', 'Psalm 4')]
    stub([], detail)
    open('/divine-office/saved/s1')
    await userEvent.click(await screen.findByRole('button', { name: /Remove from Saved Prayers/ }))
    await waitFor(() => expect(calls.some(call => call.method === 'DELETE' && call.path === '/divine-office/saved/s1')).toBe(true))
    expect(await screen.findByRole('heading', { name: 'The Oratory' })).toBeInTheDocument()
  })

  it('says plainly when the saved prayer is gone', async () => {
    stub([], 404)
    open('/divine-office/saved/missing')
    expect(await screen.findByText('This saved prayer isn’t available')).toBeInTheDocument()
  })
})
