import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { Project, ProjectDetail, ProjectUpdate, Task, WorkSession } from '../types'

const stamp = '2026-11-06T10:00:00Z'
const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()
const task = (id: string, title: string): Task => ({
  id, title, user_id: 'user', project_id: 'p1', project_name: 'Write the book', milestone_id: null, project_position: 0, description: null, status: 'todo', task_kind: 'checklist',
  due_date: null, scheduled_date: null, estimated_minutes: null, next_action: null, previous_status: null, blocked_reason: null, waiting_on: null, blocked_follow_up: null, review_notes: null, reviewer_name: null, review_requested_at: null,  created_at: stamp, updated_at: stamp, completed_at: null, steps: [],
})
const session = (fields: Partial<WorkSession>): WorkSession => ({
  id: 's1', project_id: 'p1', project_name: 'Write the book', task_id: null, task_title: null, intention: 'Outline chapter two', status: 'active',
  started_at: minutesAgo(10), ended_at: null, planned_minutes: null, elapsed_seconds: null, accomplished: null, resume_note: null, ...fields,
})
const base: Project = {
  id: 'p1', name: 'Write the book', description: 'Finish a first draft', category: null, status: 'active', target_date: null, next_action: 'Outline chapter two',
  created_at: stamp, updated_at: stamp, completed_at: null, archived_at: null, open_task_count: 1, completed_task_count: 0, milestone_count: 0, milestones_completed: 0, next_task_title: 'Draft the opening',
}
let active: WorkSession | null
let finished: WorkSession[]
let tasks: Task[]
let update: ProjectUpdate
let inboxPosts: string[]
let nextId: number
let queryClient: QueryClient
type RequestRecord = { url: string; method: string; body: Record<string, unknown> | undefined }
let requests: RequestRecord[]
const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const detail = (): ProjectDetail => ({ ...base, last_update: update, last_session: finished[0] ?? null, resume_session: finished.find(item => item.resume_note) ?? null })

beforeEach(() => {
  active = null
  finished = []
  tasks = [task('t1', 'Draft the opening')]
  update = { id: 'u1', project_id: 'p1', kind: 'session', summary: 'Wrote the first scene', next_step: 'Outline chapter two', created_at: stamp }
  inboxPosts = []
  nextId = 1
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = input.replace('/api', '')
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ url: path, method, body })
    if (path === '/projects/p1') return response(detail())
    if (path === '/projects/p1/tasks') return response(tasks)
    if (path === '/projects/p1/milestones') return response([])
    if (path === '/projects/p1/work-sessions') return response(finished)
    if (path === '/work-sessions/active') return response(active)
    if (path === '/work-sessions' && method === 'POST') {
      if (active) return response({ detail: 'A work session is already in progress' }, 409)
      active = session({ id: `new-${nextId++}`, started_at: new Date().toISOString(), intention: body.intention, task_id: body.task_id, task_title: tasks.find(t => t.id === body.task_id)?.title ?? null, planned_minutes: body.planned_minutes })
      return response(active, 201)
    }
    const finish = /^\/work-sessions\/([^/]+)\/finish$/.exec(path)
    if (finish && method === 'POST') {
      const done: WorkSession = { ...active!, status: body.interrupted ? 'interrupted' : 'finished', ended_at: body.interrupted ? null : new Date().toISOString(), elapsed_seconds: body.interrupted ? null : 600, accomplished: body.accomplished ?? null, resume_note: body.resume_note ?? null }
      finished.unshift(done)
      active = null
      return response(done)
    }
    if (path === '/inbox' && method === 'POST') { inboxPosts.push(body.content); return response({ id: `i-${nextId++}`, content: body.content, status: 'unprocessed' }, 201) }
    if (path === '/tasks') return response(tasks)
    if (path === '/inbox') return response([])
    return response({ detail: `Unhandled ${method} ${path}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })
function setup(path: string) {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}
const writes = () => requests.filter(r => r.method !== 'GET')

describe('Beginning a work session', () => {
  it('starts from a project, prefilled with its next action, with an optional duration', async () => {
    const user = setup('/projects/p1')
    await user.click(await screen.findByRole('button', { name: 'Begin Work Session' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Write the book')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('What will you work on?')).toHaveValue('Outline chapter two')
    await user.click(within(dialog).getByRole('button', { name: '25 min' }))
    await user.click(within(dialog).getByRole('button', { name: 'Begin Session' }))
    await screen.findByRole('heading', { name: 'Outline chapter two' })
    expect(writes()[0]).toEqual({ url: '/work-sessions', method: 'POST', body: { project_id: 'p1', task_id: null, intention: 'Outline chapter two', planned_minutes: 25 } })
    expect(screen.getByText('Give this your attention'.toUpperCase())).toBeInTheDocument()
    expect(screen.getByText(/25 min planned/)).toBeInTheDocument()
  })
  it('does not require a duration or a new task', async () => {
    const user = setup('/projects/p1')
    await user.click(await screen.findByRole('button', { name: 'Begin Work Session' }))
    await user.click(await screen.findByRole('button', { name: 'Begin Session' }))
    await screen.findByRole('timer')
    expect(writes()[0].body).toMatchObject({ planned_minutes: null, task_id: null })
    expect(screen.queryByText(/remaining/)).not.toBeInTheDocument()
    expect(requests.some(r => r.url === '/tasks' && r.method === 'POST')).toBe(false)
  })
  it('starts from a task, prefilled with the task title and linked to it', async () => {
    const user = setup('/projects/p1?tab=tasks')
    await user.click(await screen.findByRole('button', { name: 'Begin session: Draft the opening' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Task: Draft the opening/)).toBeInTheDocument()
    expect(within(dialog).getByLabelText('What will you work on?')).toHaveValue('Draft the opening')
    await user.click(within(dialog).getByRole('button', { name: 'Begin Session' }))
    await screen.findByRole('timer')
    expect(writes()[0].body).toEqual({ project_id: 'p1', task_id: 't1', intention: 'Draft the opening', planned_minutes: null })
    expect(screen.getByText(/Task: Draft the opening/)).toBeInTheDocument()
  })
  it('offers to resume instead of creating a duplicate active session', async () => {
    active = session({})
    const user = setup('/projects/p1')
    await screen.findByText(/A session is in progress here/)
    await user.click(screen.getByRole('button', { name: 'Begin Work Session' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('A session is already open')).toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Begin Session' })).not.toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'Resume session' })).toHaveAttribute('href', '/session')
    expect(writes()).toHaveLength(0)
  })
})

describe('The active session', () => {
  it('recovers elapsed time from the stored start time after a refresh', async () => {
    active = session({ started_at: minutesAgo(10), planned_minutes: 25 })
    setup('/session')
    const timer = await screen.findByRole('timer')
    expect(timer.textContent).toMatch(/^10:0\d$/)
    expect(screen.getByText(/1[45]:\d\d remaining/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Outline chapter two' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Write the book' })).toHaveAttribute('href', '/projects/p1')
    expect(writes()).toHaveLength(0)
  })
  it('says so kindly when no session is active', async () => {
    setup('/session')
    await screen.findByText('No session in progress')
    expect(screen.getByRole('link', { name: 'Go to projects' })).toBeInTheDocument()
  })
  it('sets a thought aside into the inbox without leaving the session or creating a task', async () => {
    active = session({})
    const user = setup('/session')
    const field = await screen.findByLabelText('Set aside for later')
    expect(field).toHaveAttribute('placeholder', 'A thought, reminder, or something to revisit…')
    await user.type(field, 'Email Sam about the archive')
    await user.click(screen.getByRole('button', { name: 'Set aside' }))
    await screen.findByText(/Set aside in your inbox/)
    expect(writes()).toEqual([{ url: '/inbox', method: 'POST', body: { content: 'Email Sam about the archive' } }])
    expect(inboxPosts).toEqual(['Email Sam about the archive'])
    expect(field).toHaveValue('')
    expect(screen.getByRole('timer')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Outline chapter two' })).toBeInTheDocument()
  })
  it('offers to end a very old session without inventing a duration', async () => {
    active = session({ started_at: minutesAgo(13 * 60) })
    const user = setup('/session')
    await user.click(await screen.findByRole('button', { name: 'End without recording time' }))
    await screen.findByRole('heading', { name: 'Write the book' })
    expect(writes()[0]).toEqual({ url: '/work-sessions/s1/finish', method: 'POST', body: { interrupted: true } })
    expect(finished[0].elapsed_seconds).toBeNull()
  })
})

describe('Finishing and resuming', () => {
  it('saves what was accomplished and where to resume, without completing the task', async () => {
    active = session({ task_id: 't1', task_title: 'Draft the opening' })
    const user = setup('/session')
    await user.click(await screen.findByRole('button', { name: 'Finish Session' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('What did you accomplish?'), 'Drafted two pages')
    await user.type(within(dialog).getByLabelText('Where should you resume next time?'), 'Start at the second scene')
    await user.click(within(dialog).getByRole('button', { name: 'Save and Finish' }))
    await screen.findByRole('heading', { name: 'Write the book' })
    expect(writes()[0]).toEqual({ url: '/work-sessions/s1/finish', method: 'POST', body: { accomplished: 'Drafted two pages', resume_note: 'Start at the second scene' } })
    expect(writes().some(r => r.url.startsWith('/tasks'))).toBe(false)
    expect(tasks[0].status).toBe('todo')
  })
  it('lets both notes stay empty, and Return to Project keeps the session open', async () => {
    active = session({})
    const user = setup('/session')
    await user.click(await screen.findByRole('button', { name: 'Finish Session' }))
    await user.click(await screen.findByRole('button', { name: 'Return to Project' }))
    await screen.findByRole('heading', { name: 'Write the book' })
    expect(writes()).toHaveLength(0)
    expect(active).not.toBeNull()
    await screen.findByText(/A session is in progress here/)
  })
  it('shows the latest session and the latest resume note in the project, beside the existing notes', async () => {
    finished = [
      session({ id: 's2', status: 'finished', intention: 'Second sitting', accomplished: 'Wrote notes', elapsed_seconds: 1800, started_at: '2026-11-06T09:00:00Z' }),
      session({ id: 's1', status: 'finished', intention: 'First sitting', accomplished: 'Read the sources', resume_note: 'Open chapter one', elapsed_seconds: 2700, started_at: '2026-11-05T09:00:00Z' }),
    ]
    const user = setup('/projects/p1')
    await screen.findByRole('heading', { name: 'Write the book' })
    const card = (await screen.findByRole('heading', { name: 'Work sessions' })).closest('.card') as HTMLElement
    expect(within(card).getByText('RESUME HERE')).toBeInTheDocument()
    expect(within(card).getByText('Open chapter one')).toBeInTheDocument()
    expect(within(card).getByText('Second sitting')).toBeInTheDocument()
    expect(within(card).getByText('Wrote notes')).toBeInTheDocument()
    expect(within(card).getByText(/30 min/)).toBeInTheDocument()
    await user.click(await within(card).findByText('Earlier sessions (1)'))
    expect(within(card).getByText('First sitting')).toBeInTheDocument()
    // existing project resume data and goal are untouched
    expect(screen.getByText('Wrote the first scene')).toBeInTheDocument()
    expect(screen.getByText('Finish a first draft')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Where I left off' })).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Begin another session' }))
    expect(await screen.findByLabelText('What will you work on?')).toBeInTheDocument()
  })
  it('invites a first session when there are none', async () => {
    setup('/projects/p1')
    await screen.findByText(/No sessions yet/)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Where I left off' })).toBeInTheDocument())
  })
})
