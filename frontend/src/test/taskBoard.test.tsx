import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { Task } from '../types'

const stamp = '2026-11-06T10:00:00Z'
const makeTask = (id: string, title: string, fields: Partial<Task> = {}): Task => ({
  id, user_id: 'u1', project_id: null, project_name: null, milestone_id: null, project_position: null,
  title, description: null, status: 'todo', task_kind: 'board', due_date: null, scheduled_date: null, estimated_minutes: null,
  next_action: null, previous_status: null, blocked_reason: null, waiting_on: null, blocked_follow_up: null,
  review_notes: null, reviewer_name: null, review_requested_at: null,
  created_at: stamp, updated_at: stamp, completed_at: null, steps: [], ...fields,
})

let tasks: Task[]
let failPatch: boolean
let failDelete: boolean
let requests: { url: string; method: string; body: unknown }[]
let queryClient: QueryClient
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  tasks = [
    makeTask('t1', 'Write the sermon', { status: 'todo', project_id: 'p1', project_name: 'Homiletics', due_date: '2026-11-20' }),
    makeTask('t2', 'Revise chapter two', { status: 'in_progress' }),
    makeTask('t3', 'Submit the essay', { status: 'in_review', review_notes: 'Check citations' }),
    makeTask('t4', 'Call the publisher', { status: 'blocked', previous_status: 'in_progress', waiting_on: 'The publisher' }),
    makeTask('t5', 'File the receipts', { status: 'completed', completed_at: stamp }),
  ]
  failPatch = false
  failDelete = false
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = new URL(input.replace('/api', ''), 'http://local')
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ url: url.pathname, method, body })
    if (url.pathname === '/tasks' && method === 'GET') return response(tasks)
    if (url.pathname.startsWith('/tasks/') && method === 'PATCH') {
      if (failPatch) return response({ detail: 'nope' }, 500)
      const id = url.pathname.split('/')[2]
      tasks = tasks.map(t => (t.id === id ? { ...t, ...body, completed_at: body.status === 'completed' ? stamp : null } : t))
      return response(tasks.find(t => t.id === id))
    }
    if (url.pathname.startsWith('/tasks/') && method === 'DELETE') {
      if (failDelete) return response({ detail: 'Could not delete' }, 500)
      tasks = tasks.filter(t => t.id !== url.pathname.split('/')[2])
      return new Response(null, { status: 204 })
    }
    if (url.pathname === '/projects') return response([{ id: 'p1', name: 'Homiletics', status: 'active' }])
    if (url.pathname === '/tasks' && method === 'POST') {
      const created = makeTask('t-new', body.title, body)
      tasks = [created, ...tasks]
      return response(created, 201)
    }
    return response({ detail: `Unhandled ${method} ${url.pathname}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })

function setup(path = '/board') {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}

const column = (name: RegExp) => screen.getByRole('listitem', { name })

describe('the Task Board', () => {
  it('lays the one task list out in five columns with counts, projects and due dates', async () => {
    setup()
    await screen.findByText('Write the sermon')
    expect(column(/To Do, 1 tasks/)).toBeInTheDocument()
    expect(column(/In Progress, 1 tasks/)).toBeInTheDocument()
    expect(column(/In Review, 1 tasks/)).toBeInTheDocument()
    expect(column(/Blocked, 1 tasks/)).toBeInTheDocument()
    expect(column(/Done, 1 tasks/)).toBeInTheDocument()
    const card = within(column(/To Do/)).getByText('Write the sermon').closest('article')!
    expect(within(card).getByText('Homiletics')).toBeInTheDocument()
    expect(within(card).getByText(/Due/)).toBeInTheDocument()
    expect(within(column(/Blocked/)).getByText(/The publisher/)).toBeInTheDocument()
  })

  it('moves a task with the keyboard-accessible status control and persists the change', async () => {
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.selectOptions(screen.getByLabelText('Status of Write the sermon'), 'in_progress')
    await waitFor(() => expect(within(column(/In Progress, 2 tasks/)).getByText('Write the sermon')).toBeInTheDocument())
    const patch = requests.find(r => r.method === 'PATCH' && r.url === '/tasks/t1')
    expect(patch?.body).toEqual({ status: 'in_progress' })
  })

  it('rolls the card back and explains when a move fails to save', async () => {
    failPatch = true
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.selectOptions(screen.getByLabelText('Status of Write the sermon'), 'completed')
    await screen.findByText(/didn’t save/)
    expect(within(column(/To Do, 1 tasks/)).getByText('Write the sermon')).toBeInTheDocument()
  })

  it('completing on the board is real completion; In Review and Blocked are not', async () => {
    const user = setup()
    await screen.findByText('Revise chapter two')
    await user.selectOptions(screen.getByLabelText('Status of Revise chapter two'), 'completed')
    await waitFor(() => expect(within(column(/Done, 2 tasks/)).getByText('Revise chapter two')).toBeInTheDocument())
    expect(tasks.find(t => t.id === 't2')?.completed_at).not.toBeNull()
    expect(tasks.find(t => t.id === 't3')?.completed_at).toBeNull()   // in_review stays unfinished
    expect(tasks.find(t => t.id === 't4')?.completed_at).toBeNull()   // blocked stays unfinished
  })

  it('offers Approve and Request changes on a card in review', async () => {
    const user = setup()
    await screen.findByText('Submit the essay')
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(requests.some(r => r.method === 'PATCH' && r.url === '/tasks/t3' && (r.body as { status: string }).status === 'completed')).toBe(true))
  })

  it('offers returning a blocked task to its previous status', async () => {
    const user = setup()
    await screen.findByText('Call the publisher')
    await user.click(screen.getByRole('button', { name: /Resume In Progress/ }))
    await waitFor(() => expect(requests.some(r => r.method === 'PATCH' && r.url === '/tasks/t4' && (r.body as { status: string }).status === 'in_progress')).toBe(true))
  })

  it('filters to one project and still lists projectless tasks on the all-tasks board', async () => {
    const user = setup()
    await screen.findByText('Revise chapter two')                     // projectless, visible by default
    await user.selectOptions(screen.getByLabelText('Filter by project'), 'p1')
    await waitFor(() => expect(screen.queryByText('Revise chapter two')).not.toBeInTheDocument())
    expect(screen.getByText('Write the sermon')).toBeInTheDocument()
  })

  it('searches task titles', async () => {
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.type(screen.getByLabelText('Search tasks'), 'publisher')
    expect(screen.queryByText('Write the sermon')).not.toBeInTheDocument()
    expect(screen.getByText('Call the publisher')).toBeInTheDocument()
  })

  it('creates a task inside a column with that column’s status preselected', async () => {
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.click(within(column(/In Review/)).getByRole('button', { name: 'Add task in In Review' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText(/Status/)).toHaveValue('in_review')
    await user.type(within(dialog).getByLabelText(/Task title/), 'Proof the galleys')
    await user.click(within(dialog).getByRole('button', { name: 'Create task' }))
    await waitFor(() => expect(requests.some(r => r.method === 'POST' && r.url === '/tasks' && (r.body as { status: string }).status === 'in_review')).toBe(true))
  })
})

describe('Daily Checklist and Task Board stay separate but share the one task system', () => {
  it('the board asks only for board tickets', async () => {
    setup()
    await screen.findByText('Write the sermon')
    expect(requests.some(r => r.url === '/tasks' && r.method === 'GET')).toBe(true)
    const fetchCalls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map(c => String(c[0]))
    expect(fetchCalls.some(u => u.includes('/tasks?kind=board'))).toBe(true)
  })

  it('a task created on the board is classified as a board ticket', async () => {
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.click(screen.getByRole('button', { name: 'Add Task' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(/Task title/), 'Plan the retreat')
    await user.click(within(dialog).getByRole('button', { name: 'Create task' }))
    await waitFor(() => expect(requests.some(r => r.method === 'POST' && (r.body as { task_kind: string }).task_kind === 'board')).toBe(true))
  })

  it('editing a ticket offers moving it to the Daily Checklist, simplifying its workflow', async () => {
    const user = setup()
    await screen.findByText('Submit the essay')          // currently in review
    await user.click(screen.getByText('Submit the essay'))     // the card body opens the editor
    const dialog = await screen.findByRole('dialog')
    await user.selectOptions(within(dialog).getByLabelText('Manage on'), 'checklist')
    expect(within(dialog).getByLabelText('Status')).toHaveValue('todo')   // mid-workflow simplified
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => {
      const patch = requests.find(r => r.method === 'PATCH' && r.url === '/tasks/t3')
      expect((patch?.body as { task_kind: string; status: string })).toMatchObject({ task_kind: 'checklist', status: 'todo' })
    })
  })
})

describe('deleting a ticket from the board', () => {
  it('asks for confirmation first and does nothing when the user keeps it', async () => {
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.click(screen.getByRole('button', { name: 'Delete task: Write the sermon' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/permanently deleted/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Keep it' }))
    expect(requests.filter(r => r.method === 'DELETE')).toHaveLength(0)
    expect(screen.getByText('Write the sermon')).toBeInTheDocument()
  })

  it('deletes through the task API and refreshes the column counts', async () => {
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.click(screen.getByRole('button', { name: 'Delete task: Write the sermon' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(screen.queryByText('Write the sermon')).not.toBeInTheDocument())
    expect(requests.some(r => r.method === 'DELETE' && r.url === '/tasks/t1')).toBe(true)
    expect(column(/To Do, 0 tasks/)).toBeInTheDocument()
  })

  it('explains a failed deletion and keeps the ticket', async () => {
    failDelete = true
    const user = setup()
    await screen.findByText('Write the sermon')
    await user.click(screen.getByRole('button', { name: 'Delete task: Write the sermon' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete permanently' }))
    expect(await within(dialog).findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Write the sermon')).toBeInTheDocument()
  })

  it('never opens the editor or starts a drag from the delete control', async () => {
    const user = setup()
    await screen.findByText('Write the sermon')
    const remove = screen.getByRole('button', { name: 'Delete task: Write the sermon' })
    const dragStart = fireEvent.dragStart(remove)        // a drag begun on the control is refused
    expect(dragStart).toBe(false)                        // preventDefault was called
    await user.click(remove)
    expect(within(await screen.findByRole('dialog')).queryByLabelText(/Task title/)).toBeNull()   // confirm, not editor
  })
})
