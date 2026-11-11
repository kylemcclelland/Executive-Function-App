import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { api } from '../services/api'
import type { InboxItem, Task } from '../types'
import { formatDate } from '../lib/utils'

const task = (id: string, title: string, fields: Partial<Task> = {}): Task => ({
  id, title, user_id: 'user', project_id: null, project_name: null, milestone_id: null, project_position: null, description: null, status: 'todo',
  due_date: null, scheduled_date: null, estimated_minutes: null, next_action: null,
  created_at: '2026-11-06T10:00:00Z', updated_at: '2026-11-06T10:00:00Z', completed_at: null, steps: [], ...fields,
})
const thought = (id: string, content: string, fields: Partial<InboxItem> = {}): InboxItem => ({
  id, content, status: 'unprocessed', converted_task_id: null, created_at: '2026-11-06T10:00:00Z', updated_at: '2026-11-06T10:00:00Z', ...fields,
})
let tasks: Task[]
let inbox: InboxItem[]
let priorities: string[]
let previous: string[]
let timezone: string
let failPath: string
let userUnsupported: boolean
let convertedCaptures: Set<string>
let nextId: number
let fetchMock: ReturnType<typeof vi.fn>
let queryClient: QueryClient
type RequestRecord = { url: string; method: string; body: Record<string, unknown> | undefined }
let requests: RequestRecord[]
const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  tasks = [task('a', 'Write the first paragraph', { next_action: 'Open the draft' }), task('b', 'Go for a walk'), task('c', 'Call the dentist'), task('d', 'Water the plants'), task('done', 'A thing already done', { status: 'completed' })]
  inbox = [thought('i1', 'A thought worth keeping')]
  priorities = []
  previous = []
  timezone = 'America/New_York'
  failPath = ''
  userUnsupported = false
  convertedCaptures = new Set()
  nextId = 1
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  fetchMock = vi.fn(async (input: string, options?: RequestInit) => {
    const url = input.replace('/api', '')
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ url, method, body })
    if (url === failPath) return response({ detail: 'The server is taking a breather. Please try again.' }, 503)
    if (url === '/today') return response({
      date: '2026-11-06', timezone, priorities: priorities.map(id => tasks.find(t => t.id === id)).filter(Boolean),
      previous_tasks: previous.map(id => tasks.find(t => t.id === id)).filter(Boolean),
      completed_tasks: tasks.filter(t => t.status === 'completed'), inbox_count: inbox.filter(i => i.status === 'unprocessed').length,
    })
    if (url === '/today/priorities') { priorities = body.task_ids; return response({}) }
    if (url === '/user') {
      if (userUnsupported) return response({ detail: 'Not found' }, 404)
      if (method === 'PATCH') timezone = body.timezone
      return response({ timezone })
    }
    if (url === '/tasks') {
      if (method === 'POST') { const created = task(`new-${nextId++}`, body.title, body); tasks.push(created); return response(created, 201) }
      return response(tasks)
    }
    if (url === '/inbox') {
      if (method === 'POST') { const created = thought(`new-${nextId++}`, body.content); inbox.unshift(created); return response(created, 201) }
      return response(inbox)
    }
    const inboxMatch = /^\/inbox\/([^/]+)(\/convert-to-task)?$/.exec(url)
    if (inboxMatch) {
      const item = inbox.find(i => i.id === inboxMatch[1])!
      if (inboxMatch[2]) {
        const created = task(`new-${nextId++}`, item.content, { description: item.content })
        tasks.push(created); item.status = 'processed'; item.converted_task_id = created.id; convertedCaptures.add(item.id)
        return response(created)
      }
      if (method === 'DELETE') { inbox = inbox.filter(i => i.id !== item.id); return response(null, 204) }
      const restoredProcessed = body?.status === 'unprocessed' && (item.converted_task_id || convertedCaptures.has(item.id))
      Object.assign(item, body, restoredProcessed ? { status: 'processed' } : {}, { updated_at: `changed-${nextId++}` })
      return response(item)
    }
    const stepMatch = /^\/tasks\/([^/]+)\/steps(?:\/([^/]+))?$/.exec(url)
    if (stepMatch) {
      const parent = tasks.find(t => t.id === stepMatch[1])!
      if (method === 'POST') { const step = { id: `step-${nextId++}`, task_id: parent.id, title: body.title, position: parent.steps.length, is_completed: false }; parent.steps.push(step); return response(step, 201) }
      const step = parent.steps.find(s => s.id === stepMatch[2])!
      if (method === 'DELETE') { parent.steps = parent.steps.filter(s => s.id !== step.id); return response(null, 204) }
      if (body.position !== undefined) {
        const other = parent.steps.find(s => s.position === body.position)
        if (other) other.position = step.position
      }
      Object.assign(step, body)
      return response(step)
    }
    const taskMatch = /^\/tasks\/([^/]+)$/.exec(url)
    if (taskMatch) {
      const item = tasks.find(t => t.id === taskMatch[1])!
      if (method === 'DELETE') { tasks = tasks.filter(t => t.id !== item.id); priorities = priorities.filter(id => id !== item.id); return response(null, 204) }
      Object.assign(item, body)
      return response(item)
    }
    return response({ detail: `Unhandled mock ${method} ${url}` }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })
function setup(path = '/') {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}
const writes = () => requests.filter(r => r.method !== 'GET')

describe('Today is intentional, not automatic', () => {
  it('starts empty, captures thoughts without creating tasks, and never auto-picks tasks', async () => {
    const user = setup()
    await screen.findByText('Choose your priorities')
    expect(writes()).toHaveLength(0)
    expect(screen.queryByRole('button', { name: 'Write the first paragraph' })).not.toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Capture a thought' }), ' Remember the library book ')
    await user.click(screen.getByRole('button', { name: 'Capture' }))
    await screen.findByText(/Saved to your inbox/)
    expect(writes()).toEqual([{ url: '/inbox', method: 'POST', body: { content: 'Remember the library book' } }])
    expect(screen.getByRole('textbox', { name: 'Capture a thought' })).toHaveValue('')
    expect(tasks).toHaveLength(5)
  })
  it('lets users select up to three incomplete tasks, reorder and remove without deleting', async () => {
    const user = setup()
    for (const title of ['Write the first paragraph', 'Go for a walk', 'Call the dentist']) {
      await user.click(await screen.findByRole('button', { name: 'Choose a priority' }))
      const dialog = screen.getByRole('dialog')
      expect(within(dialog).queryByText('A thing already done')).not.toBeInTheDocument()
      await user.click(within(dialog).getByRole('button', { name: new RegExp(title) }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    }
    expect(priorities).toEqual(['a', 'b', 'c'])
    expect(screen.queryByRole('button', { name: 'Choose a priority' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Move priority up: Call the dentist' }))
    await waitFor(() => expect(priorities).toEqual(['a', 'c', 'b']))
    await user.click(screen.getByRole('button', { name: 'Remove priority: Write the first paragraph' }))
    await waitFor(() => expect(priorities).toEqual(['c', 'b']))
    expect(tasks.some(t => t.id === 'a')).toBe(true)
    expect(writes().some(r => r.method === 'DELETE')).toBe(false)
  })
  it('carries previous incomplete choices only on explicit request', async () => {
    previous = ['b']
    const user = setup()
    await screen.findByText('Earlier tasks')
    expect(priorities).toEqual([])
    expect(writes()).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Bring to today' }))
    await waitFor(() => expect(priorities).toEqual(['b']))
    await screen.findByRole('button', { name: 'Complete task: Go for a walk' })
  })
  it('keeps the earlier-task section small and links to all unchanged tasks', async () => {
    tasks.push(task('e', 'A fifth earlier task'))
    previous = ['a', 'b', 'c', 'd', 'e']
    const user = setup()
    await screen.findByText('Earlier tasks')
    expect(screen.getAllByRole('button', { name: 'Bring to today' })).toHaveLength(3)
    expect(screen.getByText('Showing 3 of 5 earlier tasks. Nothing has been changed.')).toBeInTheDocument()
    const earlier = screen.getByText('Earlier tasks').closest('.card') as HTMLElement
    expect(within(earlier).queryByText('Water the plants')).not.toBeInTheDocument()
    expect(writes()).toHaveLength(0)
    await user.click(screen.getByRole('link', { name: 'See all tasks' }))
    await screen.findByRole('button', { name: 'Water the plants' })
    expect(screen.getByRole('button', { name: 'A fifth earlier task' })).toBeInTheDocument()
  })
  it('keeps the priority chooser open with an error and supports a successful retry', async () => {
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Choose a priority' }))
    failPath = '/today/priorities'
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Write the first paragraph/ }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('The server is taking a breather')
    expect(priorities).toEqual([])
    failPath = ''
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Write the first paragraph/ }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(priorities).toEqual(['a'])
  })
  it('preserves selected tasks when removing or reordering fails', async () => {
    priorities = ['a', 'b']
    const user = setup()
    await screen.findByRole('button', { name: 'Remove priority: Go for a walk' })
    failPath = '/today/priorities'
    await user.click(screen.getByRole('button', { name: 'Remove priority: Go for a walk' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The server is taking a breather')
    expect(priorities).toEqual(['a', 'b'])
    await user.click(screen.getByRole('button', { name: 'Move priority up: Go for a walk' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The server is taking a breather')
    expect(priorities).toEqual(['a', 'b'])
    expect(writes().some(r => r.method === 'DELETE')).toBe(false)
  })
  it('shows carry-forward errors without silently selecting an old task', async () => {
    previous = ['b']
    const user = setup()
    await screen.findByRole('button', { name: 'Bring to today' })
    failPath = '/today/priorities'
    await user.click(screen.getByRole('button', { name: 'Bring to today' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The server is taking a breather')
    expect(priorities).toEqual([])
    expect(screen.getByRole('button', { name: 'Bring to today' })).toBeEnabled()
  })
  it('allows retrying failed task-list loading inside the priority chooser', async () => {
    failPath = '/tasks'
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Choose a priority' }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('The server is taking a breather')
    failPath = ''
    await user.click(screen.getByRole('button', { name: 'Retry tasks' }))
    await within(screen.getByRole('dialog')).findByRole('button', { name: /Write the first paragraph/ })
    expect(writes()).toHaveLength(0)
  })
  it('completes directly and keeps completed items unobtrusive and reopenable', async () => {
    priorities = ['a']
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Complete task: Write the first paragraph' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Complete task: Write the first paragraph' })).not.toBeInTheDocument())
    await user.click(screen.getByText('Completed today (2)'))
    await user.click(screen.getByRole('button', { name: 'Reopen task: Write the first paragraph' }))
    await screen.findByRole('button', { name: 'Complete task: Write the first paragraph' })
    expect(tasks[0].status).toBe('todo')
  })
})

describe('Inbox lifecycle', () => {
  it('captures on Inbox and distinguishes processed and archived records', async () => {
    inbox.push(thought('i2', 'Already processed', { status: 'processed', converted_task_id: 'a' }), thought('i3', 'Archived thought', { status: 'archived' }))
    const user = setup('/inbox')
    await screen.findByText('A thought worth keeping')
    expect(screen.queryByText('Already processed')).not.toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Capture a thought' }), 'New inbox thought{Enter}')
    await screen.findByText('New inbox thought')
    await user.click(screen.getByRole('button', { name: /Processed 1/ }))
    await screen.findByText('Already processed')
    expect(screen.queryByRole('button', { name: 'Make a task' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Archived 1/ }))
    await screen.findByText('Archived thought')
  })
  it('edits, converts without replacing original text, and shows the processed record', async () => {
    const user = setup('/inbox')
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.clear(screen.getByRole('textbox', { name: 'Your thought' }))
    await user.type(screen.getByRole('textbox', { name: 'Your thought' }), 'Original text\nwith context')
    await user.click(screen.getByRole('button', { name: 'Save thought' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Make a task' }))
    await waitFor(() => expect(inbox[0].status).toBe('processed'))
    expect(writes().at(-1)).toEqual({ url: '/inbox/i1/convert-to-task', method: 'POST', body: {} })
    expect(tasks.at(-1)?.description).toBe('Original text\nwith context')
    await user.click(screen.getByRole('button', { name: /Processed 1/ }))
    expect(screen.getByText('Original text with context')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Make a task' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })
  it('archives and restores, and deletes only after confirmation', async () => {
    const user = setup('/inbox')
    await user.click(await screen.findByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(inbox[0].status).toBe('archived'))
    await user.click(screen.getByRole('button', { name: /Archived 1/ }))
    await user.click(screen.getByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(inbox[0].status).toBe('unprocessed'))
    await user.click(screen.getByRole('button', { name: /Unprocessed 1/ }))
    await user.click(screen.getByRole('button', { name: /Delete thought/ }))
    expect(inbox).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(inbox).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: /Delete thought/ }))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(inbox).toHaveLength(0))
  })
  it('restores archived converted thoughts using the accepted unprocessed request', async () => {
    inbox = [thought('i1', 'An immutable original', { status: 'archived', converted_task_id: 'a' })]
    const user = setup('/inbox')
    await user.click(screen.getByRole('button', { name: /Archived/ }))
    await screen.findByText('An immutable original')
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(inbox[0].status).toBe('processed'))
    expect(writes()[0]).toEqual({ url: '/inbox/i1', method: 'PATCH', body: { status: 'unprocessed' } })
    await user.click(screen.getByRole('button', { name: /Processed 1/ }))
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Make a task' })).not.toBeInTheDocument()
  })
  it('archives and restores a converted tombstone without editing or reprocessing it', async () => {
    inbox = [thought('i1', 'Original after task deletion', { status: 'processed', converted_task_id: null })]
    convertedCaptures.add('i1')
    const user = setup('/inbox')
    await user.click(screen.getByRole('button', { name: /Processed/ }))
    await screen.findByText('Original after task deletion')
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(inbox[0].status).toBe('archived'))
    await user.click(screen.getByRole('button', { name: /Archived 1/ }))
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(inbox[0].status).toBe('processed'))
    expect(writes().at(-1)).toEqual({ url: '/inbox/i1', method: 'PATCH', body: { status: 'unprocessed' } })
    expect(inbox[0].converted_task_id).toBeNull()
    await user.click(screen.getByRole('button', { name: /Processed 1/ }))
    expect(screen.getByText('Original after task deletion')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Make a task' })).not.toBeInTheDocument()
  })
  it('keeps unsaved capture text and exposes actionable server errors', async () => {
    const user = setup('/inbox')
    await screen.findByText('A thought worth keeping')
    failPath = '/inbox'
    await user.type(screen.getByRole('textbox', { name: 'Capture a thought' }), 'Please keep these words')
    await user.click(screen.getByRole('button', { name: 'Capture' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The server is taking a breather')
    expect(screen.getByRole('textbox', { name: 'Capture a thought' })).toHaveValue('Please keep these words')
    failPath = ''
    await user.click(screen.getByRole('button', { name: 'Capture' }))
    await screen.findByText(/Saved to your inbox/)
  })
})

describe('Tasks and small steps', () => {
  it('creates a minimal task with nullable optional values', async () => {
    const user = setup('/tasks')
    await user.click(screen.getByRole('button', { name: 'New task' }))
    expect(screen.getByRole('textbox', { name: 'Task title' })).toHaveAttribute('maxlength', '300')
    await user.type(screen.getByRole('textbox', { name: 'Task title' }), 'A fresh small task')
    await user.click(screen.getByRole('button', { name: 'Create task' }))
    await screen.findByRole('button', { name: 'A fresh small task' })
    expect(writes()[0]).toEqual({ url: '/tasks', method: 'POST', body: { title: 'A fresh small task', description: null, next_action: null, due_date: null, scheduled_date: null, estimated_minutes: null, status: 'todo', project_id: null } })
  })
  it('edits all optional fields, status and next action, then clears nullable fields', async () => {
    const user = setup('/tasks')
    await user.click(await screen.findByRole('button', { name: 'Edit task: Write the first paragraph' }))
    await user.type(screen.getByRole('textbox', { name: 'Description' }), 'Useful context')
    await user.clear(screen.getByRole('textbox', { name: 'Next small action' }))
    await user.type(screen.getByRole('textbox', { name: 'Next small action' }), 'Write a single sentence')
    await user.type(screen.getByLabelText('Due date'), '2026-11-20')
    await user.type(screen.getByLabelText('Scheduled date'), '2026-11-18')
    await user.type(screen.getByRole('spinbutton', { name: 'Estimated minutes' }), '15')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'in_progress')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(tasks[0]).toMatchObject({ description: 'Useful context', next_action: 'Write a single sentence', due_date: '2026-11-20', scheduled_date: '2026-11-18', estimated_minutes: 15, status: 'in_progress', project_id: null })
    expect(screen.getByText('Write a single sentence')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Edit task: Write the first paragraph' }))
    for (const name of ['Description', 'Next small action', 'Due date', 'Scheduled date', 'Estimated minutes']) await user.clear(screen.getByLabelText(name))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(tasks[0].estimated_minutes).toBeNull())
    expect(tasks[0]).toMatchObject({ description: null, next_action: null, due_date: null, scheduled_date: null, estimated_minutes: null })
  })
  it('completes and reopens tasks and confirms destructive deletion', async () => {
    const user = setup('/tasks')
    await user.click(await screen.findByRole('button', { name: 'Complete task: Go for a walk' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Go for a walk' })).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Completed' }))
    await user.click(screen.getByRole('button', { name: 'Reopen task: Go for a walk' }))
    await waitFor(() => expect(tasks[1].status).toBe('todo'))
    await user.click(screen.getByRole('button', { name: 'Active' }))
    await user.click(screen.getByRole('button', { name: 'Delete task: Go for a walk' }))
    expect(tasks.some(t => t.id === 'b')).toBe(true)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete task: Go for a walk' }))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(tasks.some(t => t.id === 'b')).toBe(false))
  })
  it('creates, completes, reorders and deletes subtasks', async () => {
    const user = setup('/tasks')
    await user.click(await screen.findByRole('button', { name: 'Write the first paragraph' }))
    const newStep = screen.getByRole('textbox', { name: 'New step for Write the first paragraph' })
    expect(newStep).toHaveAttribute('maxlength', '300')
    await user.type(newStep, 'Open document')
    await user.click(screen.getByRole('button', { name: 'Add step' }))
    await screen.findByRole('checkbox', { name: 'Complete step: Open document' })
    await user.type(newStep, 'Write one line')
    await user.click(screen.getByRole('button', { name: 'Add step' }))
    await user.click(await screen.findByRole('checkbox', { name: 'Complete step: Open document' }))
    await waitFor(() => expect(tasks[0].steps[0].is_completed).toBe(true))
    await user.click(screen.getByRole('button', { name: 'Move step up: Write one line' }))
    await waitFor(() => expect(tasks[0].steps[1].position).toBe(0))
    expect(writes().at(-1)?.body).toEqual({ position: 0 })
    await user.click(screen.getByRole('button', { name: 'Delete step: Open document' }))
    expect(tasks[0].steps).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(tasks[0].steps).toHaveLength(1))
  })
  it('searches tasks and filters in-progress work', async () => {
    tasks[1].status = 'in_progress'
    const user = setup('/tasks')
    await screen.findByRole('button', { name: 'Go for a walk' })
    await user.click(screen.getByRole('button', { name: 'In progress' }))
    expect(screen.queryByRole('button', { name: 'Call the dentist' })).not.toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Search tasks' }), 'zzz')
    expect(screen.getByText('Nothing matches just yet')).toBeInTheDocument()
  })
})

describe('Preferences, dates, and resilient navigation', () => {
  it('uses local date-only components so dates do not shift with UTC', () => {
    expect(formatDate('2026-11-06', { year: 'numeric', month: '2-digit', day: '2-digit' })).toBe(new Date(2026, 10, 6).toLocaleDateString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit' }))
    expect(formatDate('2026-11-06')).toContain('6')
    expect(formatDate(null)).toBe('')
  })
  it('shows the saved timezone by its friendly name and saves the IANA identifier', async () => {
    const user = setup('/settings')
    const select = await screen.findByRole('combobox', { name: 'Time Zone' })
    expect(within(select).getByRole('option', { selected: true })).toHaveTextContent('Eastern Time (US & Canada)')
    expect(within(select).queryByText('America/New_York')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save timezone' })).toBeDisabled()
    await user.selectOptions(select, 'Tokyo')
    await user.click(screen.getByRole('button', { name: 'Save timezone' }))
    await screen.findByText('Timezone saved: Tokyo.')
    expect(timezone).toBe('Asia/Tokyo')
    expect(writes()).toEqual([{ url: '/user', method: 'PATCH', body: { timezone: 'Asia/Tokyo' } }])
  })
  it('treats the server default UTC as the listed UTC option', async () => {
    timezone = 'UTC'
    setup('/settings')
    const select = await screen.findByRole('combobox', { name: 'Time Zone' })
    expect(within(select).getByRole('option', { selected: true })).toHaveTextContent('Coordinated Universal Time (UTC)')
    expect(writes()).toHaveLength(0)
  })
  it('keeps a saved timezone that is not in the list, with a readable label', async () => {
    timezone = 'Asia/Kolkata'
    setup('/settings')
    const select = await screen.findByRole('combobox', { name: 'Time Zone' })
    expect(select).toHaveValue('Asia/Kolkata')
    expect(within(select).getByRole('option', { selected: true }).textContent).toMatch(/Kolkata/)
    expect(within(select).getByRole('option', { selected: true }).textContent).not.toBe('Asia/Kolkata')
    expect(writes()).toHaveLength(0)
  })
  it('reports a failed save without claiming success, and keeps the saved timezone', async () => {
    const user = setup('/settings')
    const select = await screen.findByRole('combobox', { name: 'Time Zone' })
    failPath = '/user'
    await user.selectOptions(select, 'London')
    await user.click(screen.getByRole('button', { name: 'Save timezone' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Eastern Time (US & Canada) is still in effect')
    expect(screen.queryByText(/Timezone saved/)).not.toBeInTheDocument()
    expect(timezone).toBe('America/New_York')
    failPath = ''
    await user.click(screen.getByRole('button', { name: 'Save timezone' }))
    await screen.findByText('Timezone saved: London.')
    expect(timezone).toBe('Europe/London')
  })
  it('shows the timezone on Today by name, without a change link', async () => {
    setup('/')
    expect(await screen.findByText('Your day follows Eastern Time (US & Canada).')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Change timezone' })).not.toBeInTheDocument()
  })
  it('gracefully explains unavailable timezone support', async () => {
    userUnsupported = true
    setup('/settings')
    expect(await screen.findByText(/Timezone preferences aren’t supported/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save timezone' })).not.toBeInTheDocument()
  })
  it('shows load failures with a working retry', async () => {
    failPath = '/tasks'
    const user = setup('/tasks')
    await screen.findByRole('alert')
    failPath = ''
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByRole('button', { name: 'Write the first paragraph' })
  })
  it('handles empty 204 responses without parsing JSON', async () => {
    await expect(api('/tasks/a', 'DELETE')).resolves.toBeUndefined()
    expect(writes()[0].method).toBe('DELETE')
  })
})
