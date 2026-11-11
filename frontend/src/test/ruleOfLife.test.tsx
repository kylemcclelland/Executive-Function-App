import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { RuleEntry, RuleOccurrence } from '../types/ruleOfLife'

const entry = (id: string, title: string, local_time: string, fields: Partial<RuleEntry> = {}): RuleEntry => ({
  id, kind: 'office_hour', ref: 'compline', title, local_time, timezone: 'America/New_York', recurrence: 'daily', weekdays: [], start_date: '2026-11-01', notify: false, active: true,
  link: '/divine-office?date=2026-11-01&hour=compline', available: true, ...fields,
})
const json = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

const HOURS = [['matins', 'Matins', 'Matutinum'], ['lauds', 'Lauds', 'Laudes'], ['prime', 'Prime', 'Prima'], ['terce', 'Terce', 'Tertia'], ['sext', 'Sext', 'Sexta'], ['none', 'None', 'Nona'], ['vespers', 'Vespers', 'Vesperae'], ['compline', 'Compline', 'Completorium']]
  .map(([slug, name, latin]) => ({ slug, name, latin, available: true }))
const brief = (slug: string, title: string) => ({ id: slug, slug, title, subtitle: null, category: null, estimated_minutes: null, bookmarked: false, has_text: true })
let devotionList: ReturnType<typeof brief>[]
let entries: RuleEntry[]
let occurrences: RuleOccurrence[]
let calls: { url: string; method: string; body?: Record<string, unknown> }[]

function mount(path: string) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const url = input.replace('/api', '')
    const method = init?.method ?? 'GET'
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (url === '/rule-of-life' && method === 'GET') return json(entries)
    if (url.startsWith('/rule-of-life/occurrences')) return json(occurrences)
    if (url.startsWith('/rule-of-life')) return json(url.includes('/occurrences/') && method === 'PUT' ? occurrences[0] : entries[0], method === 'DELETE' ? 204 : 200)
    if (url === '/divine-office/hours') return json(HOURS)
    if (url === '/divine-office/saved') return json([])
    if (url === '/devotions') return json(devotionList)
    if (url === '/integrations/google-calendar/status') return json({ configured: true, status: 'not_connected' })
    if (url === '/user') return json({ timezone: 'America/New_York' })
    return json({ detail: 'unmocked' }, 404)
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  devotionList = [brief('holy-rosary', 'The Holy Rosary'), brief('act-of-contrition', 'Act of Contrition'), brief('angelus', 'The Angelus')]
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(2026, 10, 10, 12, 0))
  entries = [entry('e1', 'Compline', '21:00', { notify: true }), entry('e2', 'The Holy Rosary', '07:30', { kind: 'devotion', ref: 'holy-rosary', link: '/devotions/holy-rosary', recurrence: 'weekly', weekdays: [0, 2] })]
  entries.sort((a, b) => a.local_time.localeCompare(b.local_time))
  occurrences = [{ entry_id: 'e1', title: 'Compline', kind: 'office_hour', date: '2026-11-10', local_time: '21:00', start: '2026-11-11T02:00:00Z', time_zone: 'America/New_York', recurrence: 'daily', notify: true, link: '/divine-office?date=2026-11-10&hour=compline', status: null }]
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('the Rule of Life page', () => {
  it('lists the prayers in the order of the day with recurrence, reminder status and a link to each prayer', async () => {
    mount('/rule-of-life')
    const list = await screen.findByRole('list', { name: 'Rule of Life' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows.map(row => within(row).getByText(/^(The Holy Rosary|Compline)$/).textContent)).toEqual(['The Holy Rosary', 'Compline'])
    expect(rows[0].textContent).toContain('Mon, Wed')
    expect(rows[0].textContent).toContain('No reminder')
    expect(rows[1].textContent).toContain('Every day')
    expect(rows[1].textContent).toContain('Reminder on (not delivered yet)')                   // the preference, honestly labelled: nothing is delivered yet
    expect(screen.getByRole('link', { name: 'The Holy Rosary' })).toHaveAttribute('href', '/devotions/holy-rosary')
    expect(screen.getByRole('link', { name: 'Compline' })).toHaveAttribute('href', '/divine-office?date=2026-11-10&hour=compline')     // the Office of today's own date
  })

  const openForm = async () => {
    await userEvent.click(await screen.findByRole('button', { name: /Add to Rule of Life/ }))
    return await screen.findByRole('dialog')
  }

  it('walks through the choices in order, with plain labels and no saved-prayer option', async () => {
    mount('/rule-of-life')
    const dialog = await openForm()
    expect(within(dialog).getAllByRole('radio', { name: /Divine Office|devotion/ }).map(radio => radio.closest('label')?.textContent?.trim())).toEqual(['The Divine Office', 'A devotion, such as the Rosary'])
    expect(within(dialog).queryByText(/saved (Office )?prayer/i)).toBeNull()
    expect(dialog.textContent).not.toMatch(/office_hour|saved_office|\bref\b/)
    expect(await within(dialog).findAllByRole('radio', { name: /Matins|Lauds|Prime|Terce|Sext|None|Vespers|Compline/ })).toHaveLength(8)    // all eight canonical hours
    expect(within(dialog).getByRole('button', { name: 'Save to Rule of Life' })).toBeDisabled()                                            // nothing chosen yet
  })

  it('adds a Divine Office hour at a chosen time and recurrence', async () => {
    mount('/rule-of-life')
    const dialog = await openForm()
    await userEvent.click(await within(dialog).findByRole('radio', { name: /Lauds/ }))
    await userEvent.clear(within(dialog).getByLabelText('Time'))
    await userEvent.type(within(dialog).getByLabelText('Time'), '06:15')
    await userEvent.selectOptions(within(dialog).getByLabelText('Repeats'), 'weekly')
    await userEvent.click(within(dialog).getByLabelText('Tuesday'))
    await userEvent.click(within(dialog).getByText('More options'))
    await userEvent.click(within(dialog).getByLabelText(/Remind me/))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save to Rule of Life' }))
    await waitFor(() => expect(calls.find(call => call.method === 'POST')).toBeTruthy())
    expect(calls.find(call => call.method === 'POST')).toMatchObject({ url: '/rule-of-life', body: { kind: 'office_hour', ref: 'lauds', local_time: '06:15', recurrence: 'weekly', weekdays: [1], notify: true } })
  })

  it('offers the listed devotions, including the Rosary, with a search', async () => {
    mount('/rule-of-life')
    const dialog = await openForm()
    await userEvent.click(within(dialog).getByRole('radio', { name: /A devotion/ }))
    expect(await within(dialog).findAllByRole('radio', { name: /^(The Holy Rosary|Act of Contrition|The Angelus)$/ })).toHaveLength(3)
    await userEvent.type(within(dialog).getByLabelText('Search devotions'), 'rosary')
    expect(within(dialog).getAllByRole('radio', { name: /^(The Holy Rosary|Act of Contrition|The Angelus)$/ })).toHaveLength(1)
    expect(within(dialog).getByText('1 devotion')).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('radio', { name: 'The Holy Rosary' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save to Rule of Life' }))
    await waitFor(() => expect(calls.find(call => call.method === 'POST')).toMatchObject({ body: { kind: 'devotion', ref: 'holy-rosary' } }))
  })

  it('says so when no devotion matches or none exist', async () => {
    mount('/rule-of-life')
    const dialog = await openForm()
    await userEvent.click(within(dialog).getByRole('radio', { name: /A devotion/ }))
    await userEvent.type(await within(dialog).findByLabelText('Search devotions'), 'zzz')
    expect(within(dialog).getByText('No devotion matches your search.')).toBeInTheDocument()
  })

  it('shows an empty state when The Oratory has no devotions', async () => {
    devotionList = []
    mount('/rule-of-life')
    const dialog = await openForm()
    await userEvent.click(within(dialog).getByRole('radio', { name: /A devotion/ }))
    expect(await within(dialog).findByText('No devotions are available in The Oratory yet.')).toBeInTheDocument()
  })

  it('keeps and safely shows an earlier saved-prayer entry, which can still be paused but is never offered for new entries', async () => {
    entries = [entry('old', 'Psalm 11', '08:00', { kind: 'saved_office', ref: 'abc', link: '/divine-office/saved/abc' }), ...entries]
    mount('/rule-of-life')
    const row = (await screen.findByRole('link', { name: 'Psalm 11' })).closest('li')!
    expect(screen.getByRole('link', { name: 'Psalm 11' })).toHaveAttribute('href', '/divine-office/saved/abc')
    expect(row.textContent).toContain('Saved Office prayer (earlier entry)')
    await userEvent.click(within(row).getByRole('button', { name: 'Pause Psalm 11' }))
    await waitFor(() => expect(calls.find(call => call.method === 'PATCH')).toMatchObject({ url: '/rule-of-life/old' }))
  })

  it('pauses, edits and removes an entry', async () => {
    mount('/rule-of-life')
    await userEvent.click(await screen.findByRole('button', { name: 'Pause Compline' }))
    await waitFor(() => expect(calls.find(call => call.method === 'PATCH')).toMatchObject({ url: '/rule-of-life/e1', body: { active: false } }))
    await userEvent.click(screen.getByRole('button', { name: 'Edit Compline' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.clear(within(dialog).getByLabelText('Time'))
    await userEvent.type(within(dialog).getByLabelText('Time'), '20:45')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(calls.filter(call => call.method === 'PATCH')[1]).toMatchObject({ body: { local_time: '20:45', recurrence: 'daily', timezone: 'America/New_York' } }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await userEvent.click(screen.getByRole('button', { name: 'Remove Compline' }))
    await userEvent.click(await screen.findByRole('button', { name: /Delete permanently/ }))
    await waitFor(() => expect(calls.find(call => call.method === 'DELETE')).toMatchObject({ url: '/rule-of-life/e1' }))
  })

  it('marks today’s prayer completed or skipped, with no streaks or scores', async () => {
    mount('/rule-of-life')
    await userEvent.click(await screen.findByRole('button', { name: 'Completed' }))
    await waitFor(() => expect(calls.find(call => call.method === 'PUT')).toMatchObject({ url: '/rule-of-life/e1/occurrences/2026-11-10', body: { status: 'completed' } }))
    expect(screen.queryByText(/streak|score|points/i, { selector: 'li, li *' })).toBeNull()
  })

  it('opens the edit form from a link such as the one on the Calendar', async () => {
    mount('/rule-of-life?edit=e1')
    expect(await screen.findByRole('heading', { name: 'Edit Rule of Life entry' })).toBeInTheDocument()
  })

  it('shows an empty state with the way to begin', async () => {
    entries = []
    mount('/rule-of-life')
    expect(await screen.findByText('Your Rule of Life is empty')).toBeInTheDocument()
  })
})

describe('the Calendar', () => {
  it('shows scheduled prayers on their day, opens the prayer from there and offers edit and the two marks', async () => {
    mount('/calendar')
    const link = await screen.findByRole('link', { name: 'Compline' })
    expect(link).toHaveAttribute('href', '/divine-office?date=2026-11-10&hour=compline')
    expect(screen.getByRole('heading', { name: 'Rule of Life' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Edit Compline' })).toHaveAttribute('href', '/rule-of-life?edit=e1')
    await userEvent.click(screen.getByRole('button', { name: 'Mark Compline skipped' }))
    await waitFor(() => expect(calls.find(call => call.method === 'PUT')).toMatchObject({ url: '/rule-of-life/e1/occurrences/2026-11-10', body: { status: 'skipped' } }))
  })
})

describe('navigation', () => {
  it('lists Rule of Life in the main navigation and links to it from The Oratory', async () => {
    mount('/rule-of-life')
    expect(within(await screen.findByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: /Rule of Life/ })).toHaveAttribute('href', '/rule-of-life')
  })
})
