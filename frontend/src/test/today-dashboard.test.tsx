import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { NoteBrief, Task } from '../types'

const task = (id: string, title: string, fields: Partial<Task> = {}): Task => ({
  id, title, user_id: 'u', project_id: null, project_name: null, milestone_id: null, project_position: null, description: null, status: 'todo',
  due_date: null, scheduled_date: null, estimated_minutes: null, next_action: null,
  created_at: '2030-03-05T10:00:00Z', updated_at: '2030-03-05T10:00:00Z', completed_at: null, steps: [], ...fields,
})
const json = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

let tasks: Task[]
let calendar: unknown
let priorities: string[]
let notes: NoteBrief[] | 'fail'
let books: { items: { id: string; title: string; authors: string[] }[]; total: number } | 'fail'
let requests: { url: string; method: string; body?: Record<string, unknown> }[]
let queryClient: QueryClient

beforeEach(() => {
  calendar = null
  tasks = [task('a', 'Write the first paragraph'), task('b', 'Water the plants', { next_action: 'Fill the can' }), task('c', 'Call the dentist'), task('d', 'Mail the letter'), task('done', 'Already finished', { status: 'completed' })]
  priorities = []
  notes = [{ id: 'n1', title: 'On attention', note_type: 'reflection', book_id: null, book_title: 'The Imitation of Christ', project_id: null, project_name: null, source_location: null, tags: [], excerpt: '', updated_at: '2030-03-05T10:00:00Z' }]
  books = { items: [{ id: 'b1', title: 'Confessions', authors: ['Augustine'] }, { id: 'b2', title: 'The Rule of St Benedict', authors: [] }], total: 2170 }
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = input.replace('/api', '')
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ url, method, body })
    if (url === '/today') return json({ date: '2030-03-05', timezone: 'UTC', priorities: priorities.map(id => tasks.find(t => t.id === id)), previous_tasks: [], completed_tasks: [], inbox_count: 2 })
    if (url === '/today/priorities') { priorities = body.task_ids; return json({}) }
    if (url === '/tasks' && method === 'POST') { const created = task(`new-${tasks.length}`, body.title); tasks.push(created); return json(created, 201) }
    if (url === '/tasks') return json(tasks)
    const patch = /^\/tasks\/([^/]+)$/.exec(url)
    if (patch && method === 'PATCH') { Object.assign(tasks.find(t => t.id === patch[1])!, body); return json({}) }
    if (url.startsWith('/notes')) return notes === 'fail' ? json({ detail: 'x' }, 500) : json(notes)
    if (url.startsWith('/books')) return books === 'fail' ? json({ detail: 'x' }, 500) : json({ ...books, page: 1, page_size: 3, total_pages: 1 })
    if (url.startsWith('/liturgical-calendar/')) return calendar === null ? json({ detail: 'The liturgical calendar is unavailable' }, 503) : json(calendar)
    if (url === '/integrations/google-calendar/status') return json({ configured: false, status: 'not_connected', account_email: null, connected_at: null, last_successful_sync_at: null })
    return json({ detail: `Unhandled ${method} ${url}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })

function setup() {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}
const writes = () => requests.filter(r => r.method !== 'GET')

describe('Today dashboard', () => {
  it('greets the user, dates the page and carries the motto', async () => {
    setup()
    expect(await screen.findByText('Tuesday, March 5')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
    expect(screen.getByText(/Good (morning|afternoon|evening)\. Choose what matters/)).toBeInTheDocument()
    expect(screen.getAllByText('Unum est necessarium').length).toBeGreaterThan(0)
  })

  it('puts the priorities first, ahead of tasks, with the three-priority limit intact', async () => {
    const user = setup()
    const heading = await screen.findByRole('heading', { name: /Today’s Priorities/ })
    const tasksHeading = await screen.findByRole('heading', { name: /^Tasks/ })
    expect(heading.compareDocumentPosition(tasksHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(heading).toHaveTextContent('0 / 3')
    for (const title of ['Write the first paragraph', 'Water the plants', 'Call the dentist']) {
      await user.click(await screen.findByRole('button', { name: 'Choose a priority' }))
      await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: new RegExp(title) }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    }
    expect(priorities).toHaveLength(3)
    expect(screen.queryByRole('button', { name: 'Choose a priority' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Make a priority: Mail the letter' })).toBeDisabled()
  })

  it('lists open tasks apart from the priorities, never auto-selecting any', async () => {
    setup()
    const card = (await screen.findByRole('heading', { name: /^Tasks/ })).closest('.card') as HTMLElement
    expect(await within(card).findByText('4 open')).toBeInTheDocument()
    for (const title of ['Write the first paragraph', 'Water the plants', 'Call the dentist', 'Mail the letter']) expect(within(card).getByText(title)).toBeInTheDocument()
    expect(within(card).queryByText('Already finished')).not.toBeInTheDocument()
    expect(within(card).getByText('Fill the can')).toBeInTheDocument()
    expect(writes()).toHaveLength(0)
  })

  it('moves a task into the priorities only on request, and keeps it out of the task list afterwards', async () => {
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Make a priority: Water the plants' }))
    await waitFor(() => expect(priorities).toEqual(['b']))
    const card = screen.getByRole('heading', { name: /^Tasks/ }).closest('.card') as HTMLElement
    await waitFor(() => expect(within(card).queryByText('Water the plants')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Complete task: Water the plants' })).toBeInTheDocument()
  })

  it('adds a task with quick-add, trimmed, and clears the field', async () => {
    const user = setup()
    const field = await screen.findByRole('textbox', { name: 'Add a task' })
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
    await user.type(field, '  Buy candles  ')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(writes()).toEqual([{ url: '/tasks', method: 'POST', body: { title: 'Buy candles' } }]))
    await screen.findByText('Buy candles')
    expect(field).toHaveValue('')
  })

  it('completes a task from the list', async () => {
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Mark complete: Mail the letter' }))
    await waitFor(() => expect(writes()).toEqual([{ url: '/tasks/d', method: 'PATCH', body: { status: 'completed' } }]))
    const card = screen.getByRole('heading', { name: /^Tasks/ }).closest('.card') as HTMLElement
    await waitFor(() => expect(within(card).queryByText('Mail the letter')).not.toBeInTheDocument())
  })

  it('shows at most five tasks and links to the rest', async () => {
    for (let i = 0; i < 4; i++) tasks.push(task(`x${i}`, `Extra ${i}`))
    setup()
    const card = (await screen.findByRole('heading', { name: /^Tasks/ })).closest('.card') as HTMLElement
    expect(await within(card).findByText('8 open')).toBeInTheDocument()
    expect(within(card).getAllByRole('button', { name: /^Mark complete:/ })).toHaveLength(5)
    expect(within(card).getByRole('link', { name: 'See all 8 tasks' })).toHaveAttribute('href', '/tasks')
  })

  it('shows recent books and notes with links, never reading progress it does not have', async () => {
    setup()
    const card = (await screen.findByRole('heading', { name: /Reading/ })).closest('.card') as HTMLElement
    expect(await within(card).findByText('Confessions')).toBeInTheDocument()
    expect(within(card).getByText('Augustine')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /On attention/ })).toHaveAttribute('href', '/notes/n1')
    expect(within(card).getByText('Reflection · The Imitation of Christ')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Library \(2,170\)/ })).toHaveAttribute('href', '/library')
    expect(within(card).queryByText(/progress|%|pages? read/i)).not.toBeInTheDocument()
    expect(requests.some(r => r.url === '/books?page_size=3&sort=recent')).toBe(true)
  })

  it('invites the first book or note when there are none, and hides itself on errors', async () => {
    books = { items: [], total: 0 }
    notes = []
    const first = setup()
    expect(await screen.findByText('Books you add and notes you write will gather here.')).toBeInTheDocument()
    void first
  })

  it('renders without the reading card if both lookups fail', async () => {
    books = 'fail'
    notes = 'fail'
    setup()
    await screen.findByRole('heading', { name: /Today’s Priorities/ })
    await waitFor(() => expect(requests.some(r => r.url.startsWith('/notes'))).toBe(true))
    await waitFor(() => expect(screen.queryByRole('heading', { name: /Reading/ })).not.toBeInTheDocument())
  })

  it('shows the traditional calendar card near the top of Today, above the priorities, and keeps the other features', async () => {
    calendar = { date: '2030-03-05', edition: 'roman_1960', celebration: 'Filler Feast', celebration_latin: 'Fillerii', celebration_type: 'feast', type_label: 'Feast', qualifier: null, rank: 'I. classis', rank_class: 'I', rank_label: 'I Class', season: 'Lent', season_code: 'Quad1', commemorations: [], description: null, engine: { name: 'Divinum Officium', url: 'https://example.org', commit: null, version: 'Rubrics 1960 - 1960' } }
    setup()
    const card = (await screen.findByRole('heading', { name: 'Filler Feast' })).closest('.calendar-card') as HTMLElement
    const priorities = await screen.findByRole('heading', { name: /Today’s Priorities/ })
    expect(card.compareDocumentPosition(priorities) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(card).getByRole('link', { name: /Read Today’s Divine Office/ })).toHaveAttribute('href', expect.stringMatching(/^\/divine-office\?date=\d{4}-\d{2}-\d{2}$/))
    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
    expect(await screen.findByText('Water the plants')).toBeInTheDocument()
  })

  it('still loads Today completely when the traditional calendar is unavailable', async () => {
    setup()
    expect(await screen.findByText(/The traditional calendar is unavailable right now/)).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /Today’s Priorities/ })).toBeInTheDocument()
    expect(await screen.findByText('Water the plants')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('replaces the reserved Living Liturgically placeholder with the traditional calendar card', async () => {
    setup()
    await screen.findByRole('heading', { name: /Today’s Priorities/ })
    expect(screen.queryByText('Living Liturgically')).toBeNull()
    expect(screen.queryByText('Coming later')).toBeNull()
    expect(await screen.findByText('Traditional Liturgical Calendar')).toBeInTheDocument()
  })
})
