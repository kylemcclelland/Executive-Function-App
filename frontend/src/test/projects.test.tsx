import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { Milestone, Project, ProjectNote, ProjectUpdate, Task } from '../types'

const stamp = '2026-11-06T10:00:00Z'
const task = (id: string, title: string, fields: Partial<Task> = {}): Task => ({
  id, title, user_id: 'user', project_id: null, project_name: null, milestone_id: null, project_position: null, description: null, status: 'todo',
  due_date: null, scheduled_date: null, estimated_minutes: null, next_action: null, created_at: stamp, updated_at: stamp, completed_at: null, steps: [], ...fields,
})
const project = (id: string, name: string, fields: Partial<Project> = {}): Project => ({
  id, name, description: null, category: null, status: 'active', target_date: null, next_action: null, created_at: stamp, updated_at: stamp,
  completed_at: null, archived_at: null, open_task_count: 0, completed_task_count: 0, milestone_count: 0, milestones_completed: 0, next_task_title: null, ...fields,
})
let projects: Project[]
let tasks: Task[]
let notes: ProjectNote[]
let milestones: Milestone[]
let updates: ProjectUpdate[]
let nextId: number
let queryClient: QueryClient
type RequestRecord = { url: string; method: string; body: Record<string, unknown> | undefined }
let requests: RequestRecord[]
const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const withCounts = (item: Project): Project => {
  const own = tasks.filter(t => t.project_id === item.id)
  const open = own.filter(t => t.status !== 'completed')
  const mine = milestones.filter(m => m.project_id === item.id)
  return { ...item, open_task_count: open.length, completed_task_count: own.length - open.length, next_task_title: open[0]?.title ?? null, milestone_count: mine.length, milestones_completed: mine.filter(m => m.completed_at).length }
}
const detail = (item: Project) => ({ ...withCounts(item), last_update: updates.filter(u => u.project_id === item.id).at(-1) ?? null })

beforeEach(() => {
  projects = [
    project('p1', 'Write the book', { description: 'Finish a first draft', category: 'Writing', next_action: 'Outline chapter two' }),
    project('p2', 'Learn Japanese', { status: 'someday' }),
    project('p3', 'Old garden plan', { archived_at: stamp }),
  ]
  tasks = [
    task('t1', 'Draft the opening', { project_id: 'p1', project_name: 'Write the book', project_position: 0 }),
    task('t2', 'Interview a neighbour', { project_id: 'p1', project_name: 'Write the book', project_position: 1 }),
    task('t3', 'Buy a notebook'),
    task('t4', 'Book the dentist', { project_id: 'p2', project_name: 'Learn Japanese', project_position: 0 }),
  ]
  notes = [{ id: 'n1', project_id: 'p1', title: 'Sources', content: 'The library has a copy', created_at: stamp, updated_at: stamp }]
  milestones = [{ id: 'm1', project_id: 'p1', title: 'First draft', description: null, target_date: null, position: 0, completed_at: null, task_count: 0, completed_task_count: 0 }]
  updates = [{ id: 'u1', project_id: 'p1', kind: 'session', summary: 'Wrote the first scene', next_step: 'Outline chapter two', created_at: stamp }]
  nextId = 1
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = new URL(input.replace('/api', ''), 'http://local')
    const path = url.pathname
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ url: path + url.search, method, body })
    if (path === '/today') return response({ date: '2026-11-06', timezone: 'UTC', priorities: [], previous_tasks: [], completed_tasks: [], inbox_count: 0, active_projects: projects.filter(p => p.status === 'active' && !p.archived_at).map(withCounts) })
    if (path === '/tasks') {
      if (method === 'POST') { const created = task(`new-${nextId++}`, body.title, { ...body, project_name: projects.find(p => p.id === body.project_id)?.name ?? null, project_position: body.project_id ? tasks.filter(t => t.project_id === body.project_id).length : null }); tasks.push(created); return response(created, 201) }
      return response(tasks)
    }
    const taskMatch = /^\/tasks\/([^/]+)$/.exec(path)
    if (taskMatch) {
      const item = tasks.find(t => t.id === taskMatch[1])!
      if (body.status) item.completed_at = body.status === 'completed' ? stamp : null
      if (body.project_id === null) { item.project_name = null; item.project_position = null }
      Object.assign(item, body)
      return response(item)
    }
    if (path === '/projects') {
      if (method === 'POST') { const created = project(`new-${nextId++}`, body.name, body); projects.unshift(created); return response(detail(created), 201) }
      const term = url.searchParams.get('q')?.toLowerCase()
      const status = url.searchParams.get('status')
      const archived = url.searchParams.get('archived') === 'true'
      return response(projects.filter(p => (archived ? p.archived_at : !p.archived_at) && (!status || p.status === status) && (!term || `${p.name} ${p.description ?? ''}`.toLowerCase().includes(term))).map(withCounts))
    }
    const match = /^\/projects\/([^/]+)(?:\/(tasks|milestones|notes|updates|history)(?:\/([^/]+))?)?$/.exec(path)
    if (!match) return response({ detail: `Unhandled ${method} ${path}` }, 404)
    const [, id, section, child] = match
    const item = projects.find(p => p.id === id)
    if (!item) return response({ detail: 'Project not found' }, 404)
    if (!section) {
      if (method === 'DELETE') { projects = projects.filter(p => p.id !== id); tasks.forEach(t => { if (t.project_id === id) t.project_id = null }); return response(null, 204) }
      if (method === 'PATCH') {
        const { archived, ...rest } = body
        Object.assign(item, rest)
        if (archived !== undefined) item.archived_at = archived ? stamp : null
      }
      return response(detail(item))
    }
    if (section === 'tasks') {
      if (child === 'order') { body.task_ids.forEach((taskId: string, index: number) => { tasks.find(t => t.id === taskId)!.project_position = index }); }
      if (method === 'POST') body.task_ids.forEach((taskId: string) => Object.assign(tasks.find(t => t.id === taskId)!, { project_id: id, project_name: item.name, project_position: tasks.filter(t => t.project_id === id).length }))
      return response(tasks.filter(t => t.project_id === id).sort((a, b) => (a.project_position ?? 0) - (b.project_position ?? 0)))
    }
    if (section === 'milestones') {
      if (method === 'POST') { const created: Milestone = { id: `new-${nextId++}`, project_id: id, description: null, target_date: null, position: milestones.length, completed_at: null, task_count: 0, completed_task_count: 0, ...body }; milestones.push(created); return response(created, 201) }
      const found = milestones.find(m => m.id === child)
      if (found && method === 'PATCH') { if (body.completed !== undefined) found.completed_at = body.completed ? stamp : null; return response(found) }
      return response(milestones.filter(m => m.project_id === id))
    }
    if (section === 'notes') {
      if (method === 'POST') { const created: ProjectNote = { id: `new-${nextId++}`, project_id: id, created_at: stamp, updated_at: stamp, ...body }; notes.push(created); return response(created, 201) }
      if (method === 'DELETE') { notes = notes.filter(n => n.id !== child); return response(null, 204) }
      const term = url.searchParams.get('q')?.toLowerCase()
      return response(notes.filter(n => n.project_id === id && (!term || `${n.title ?? ''} ${n.content}`.toLowerCase().includes(term))))
    }
    if (section === 'updates') {
      const created: ProjectUpdate = { id: `new-${nextId++}`, project_id: id, created_at: stamp, ...body }
      updates.push(created)
      if (body.next_step) item.next_action = body.next_step
      return response(created, 201)
    }
    return response(updates.map(u => ({ id: u.id, type: u.kind, at: u.created_at, title: u.summary, next_step: u.next_step })))
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })
function setup(path: string) {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}
const writes = () => requests.filter(r => r.method !== 'GET')

describe('Projects dashboard', () => {
  it('shows each project’s next action and remaining tasks without deadlines or scores', async () => {
    setup('/projects')
    const card = (await screen.findByRole('link', { name: 'Write the book' })).closest('.project-card') as HTMLElement
    expect(within(card).getByText('Outline chapter two')).toBeInTheDocument()
    expect(within(card).getByText('2 tasks remaining')).toBeInTheDocument()
    expect(within(card).getByText('Writing')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Learn Japanese' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Old garden plan' })).not.toBeInTheDocument()
    expect(screen.queryByText(/overdue|late|failed|streak|score/i)).not.toBeInTheDocument()
  })
  it('creates a project from only a name and opens its workspace', async () => {
    const user = setup('/projects')
    await user.click(await screen.findByRole('button', { name: 'New project' }))
    await user.type(screen.getByLabelText('Project name'), '  Plan the trip ')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    await screen.findByRole('heading', { name: 'Plan the trip' })
    expect(writes()[0]).toEqual({ url: '/projects', method: 'POST', body: { name: 'Plan the trip', description: null, category: null, status: 'active', target_date: null, next_action: null } })
  })
  it('filters by status, searches, and shows archived projects separately', async () => {
    const user = setup('/projects')
    await screen.findByRole('link', { name: 'Write the book' })
    await user.click(screen.getByRole('button', { name: 'Someday' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Write the book' })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'Learn Japanese' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'All' }))
    await user.type(screen.getByRole('textbox', { name: 'Search projects' }), 'book')
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Learn Japanese' })).not.toBeInTheDocument())
    await user.clear(screen.getByRole('textbox', { name: 'Search projects' }))
    await user.click(screen.getByRole('button', { name: 'Archived' }))
    await screen.findByRole('link', { name: 'Old garden plan' })
    expect(requests.some(r => r.url === '/projects?archived=true')).toBe(true)
    expect(requests.some(r => r.url === '/projects?status=someday')).toBe(true)
    expect(requests.some(r => r.url === '/projects?q=book')).toBe(true)
  })
  it('archives and edits from the card, and deleting asks first without touching tasks', async () => {
    const user = setup('/projects')
    await user.click(await screen.findByRole('button', { name: 'Archive project: Write the book' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Write the book' })).not.toBeInTheDocument())
    expect(writes()[0]).toEqual({ url: '/projects/p1', method: 'PATCH', body: { archived: true } })
    await user.click(screen.getByRole('button', { name: 'Edit project: Learn Japanese' }))
    await user.clear(screen.getByLabelText('Project name'))
    await user.type(screen.getByLabelText('Project name'), 'Learn Spanish')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('link', { name: 'Learn Spanish' })
    await user.click(screen.getByRole('button', { name: 'Delete project: Learn Spanish' }))
    expect(screen.getByText(/permanently deleted/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(writes().some(r => r.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Delete project: Learn Spanish' }))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Learn Spanish' })).not.toBeInTheDocument())
    expect(tasks).toHaveLength(4)
  })
})

describe('Project workspace', () => {
  it('lets you resume: goal, next action, last session and upcoming tasks', async () => {
    const user = setup('/projects/p1')
    await screen.findByRole('heading', { name: 'Write the book' })
    expect(screen.getByText('Finish a first draft')).toBeInTheDocument()
    expect(screen.getByText('Wrote the first scene')).toBeInTheDocument()
    expect(screen.getByText('Next: Outline chapter two')).toBeInTheDocument()
    expect(screen.getByText('Draft the opening')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save your place' }))
    await user.type(screen.getByLabelText('What did you accomplish?'), 'Interviewed Sam')
    await user.type(screen.getByLabelText('What should you do next?'), 'Transcribe the recording')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(writes()[0]).toEqual({ url: '/projects/p1/updates', method: 'POST', body: { kind: 'session', summary: 'Interviewed Sam', next_step: 'Transcribe the recording' } })
    await screen.findByText('Interviewed Sam')
    expect(screen.getAllByText(/Transcribe the recording/).length).toBeGreaterThan(0)
  })
  it('edits the next action and offers the first task when none is chosen', async () => {
    const user = setup('/projects/p2')
    await screen.findByRole('heading', { name: 'Learn Japanese' })
    await user.click(screen.getByRole('button', { name: 'Use that task' }))
    expect(writes()[0]).toEqual({ url: '/projects/p2', method: 'PATCH', body: { next_action: 'Book the dentist' } })
    await user.click(await screen.findByRole('button', { name: 'Change' }))
    await user.clear(screen.getByLabelText('Next action'))
    await user.type(screen.getByLabelText('Next action'), 'Open the textbook')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText('Open the textbook')
  })
  it('changes status quickly without requiring any other field', async () => {
    const user = setup('/projects/p1')
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Project status' }), 'paused')
    expect(writes()[0]).toEqual({ url: '/projects/p1', method: 'PATCH', body: { status: 'paused' } })
  })
  it('creates tasks inside the project, links existing tasks, reorders and completes them', async () => {
    const user = setup('/projects/p1?tab=tasks')
    await screen.findByText('Draft the opening')
    await user.click(screen.getByRole('button', { name: 'New task' }))
    await user.type(screen.getByLabelText('Task title'), 'Collect photos')
    await user.selectOptions(screen.getByLabelText('Milestone'), 'm1')
    await user.click(screen.getByRole('button', { name: 'Create task' }))
    await screen.findByText('Collect photos')
    expect(writes()[0].body).toMatchObject({ title: 'Collect photos', project_id: 'p1', milestone_id: 'm1' })

    await user.click(screen.getByRole('button', { name: 'Add existing tasks' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).queryByText('Draft the opening')).not.toBeInTheDocument()
    expect(within(dialog).getByText('Currently in Learn Japanese')).toBeInTheDocument()
    await user.click(within(dialog).getByLabelText(/Buy a notebook/))
    await user.click(within(dialog).getByRole('button', { name: 'Add 1 task' }))
    await screen.findByText('Buy a notebook')
    expect(writes()[1]).toEqual({ url: '/projects/p1/tasks', method: 'POST', body: { task_ids: ['t3'] } })
    expect(tasks).toHaveLength(5)

    await user.click(screen.getByRole('button', { name: 'Move task down: Draft the opening' }))
    expect(writes()[2]).toEqual({ url: '/projects/p1/tasks/order', method: 'PUT', body: { task_ids: ['t2', 't1', 'new-1', 't3'] } })

    await user.click(screen.getByRole('button', { name: 'Complete task: Draft the opening' }))
    expect(writes()[3]).toEqual({ url: '/tasks/t1', method: 'PATCH', body: { status: 'completed' } })
    await screen.findByText('Completed (1)')
    await user.click(screen.getByRole('button', { name: 'Remove from project: Buy a notebook' }))
    expect(writes()[4]).toEqual({ url: '/tasks/t3', method: 'PATCH', body: { project_id: null } })
  })
  it('creates, searches, edits and deletes notes', async () => {
    const user = setup('/projects/p1?tab=notes')
    await screen.findByText('The library has a copy')
    await user.click(screen.getByRole('button', { name: 'New note' }))
    await user.type(screen.getByLabelText('Note'), 'Ask about the archive')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await screen.findByText('Ask about the archive')
    expect(writes()[0]).toEqual({ url: '/projects/p1/notes', method: 'POST', body: { title: null, content: 'Ask about the archive' } })
    await user.type(screen.getByRole('textbox', { name: 'Search notes' }), 'archive')
    await waitFor(() => expect(screen.queryByText('The library has a copy')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /Delete note: Ask about/ }))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await screen.findByText('Nothing matches just yet')
    expect(notes.map(n => n.id)).toEqual(['n1'])
  })
  it('creates and completes milestones and shows progress', async () => {
    const user = setup('/projects/p1?tab=milestones')
    await screen.findByText('First draft')
    await user.click(screen.getByRole('button', { name: 'New milestone' }))
    await user.type(screen.getByLabelText('Milestone title'), 'Revision')
    await user.click(screen.getByRole('button', { name: 'Save milestone' }))
    await screen.findByText('Revision')
    expect(writes()[0]).toEqual({ url: '/projects/p1/milestones', method: 'POST', body: { title: 'Revision', description: null, target_date: null } })
    await user.click(screen.getByRole('button', { name: 'Complete milestone: First draft' }))
    expect(writes()[1]).toEqual({ url: '/projects/p1/milestones/m1', method: 'PATCH', body: { completed: true } })
    await screen.findByText('1 of 2 reached. Milestones are optional checkpoints; tasks can be linked to them when you edit a task.')
  })
  it('shows chronological history and lets you log from there', async () => {
    const user = setup('/projects/p1?tab=history')
    await screen.findByText('Wrote the first scene')
    expect(screen.getByText(/Work session/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Log a session' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
  it('explains a missing project kindly', async () => {
    setup('/projects/gone')
    await screen.findByText('We couldn’t find that project')
    expect(screen.getByRole('link', { name: 'Back to projects' })).toBeInTheDocument()
  })
})

describe('Integration with Today and Tasks', () => {
  it('offers only active projects on Today, as a resume prompt rather than a deadline', async () => {
    setup('/')
    const link = await screen.findByRole('link', { name: /Write the book/ })
    expect(link).toHaveAttribute('href', '/projects/p1')
    expect(screen.getByText('Next: Outline chapter two')).toBeInTheDocument()
    expect(screen.queryByText(/Learn Japanese/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Old garden plan/)).not.toBeInTheDocument()
  })
  it('labels tasks with their project on the Tasks page', async () => {
    setup('/tasks')
    await screen.findByText('Draft the opening')
    expect(screen.getAllByText('Write the book').length).toBeGreaterThan(0)
  })
})
