import { useMemo, useState, type DragEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { CalendarDays, OctagonPause, Plus, Trash2, Undo2 } from 'lucide-react'
import { api } from '../services/api'
import { ConfirmDelete, ErrorMessage, Loading, PageHeader } from '../components/common'
import { TaskEditor } from '../components/tasks/TaskEditor'
import { Button, Card, Input } from '../components/ui'
import { COLUMNS, STATUS_LABELS as LABELS } from '../lib/board'
import { formatDate } from '../lib/utils'
import type { Project, Task, TaskStatus } from '../types'


/**
 * The Task Board: the same tasks as Today, Tasks and Projects, laid out by workflow status.
 * Moving a card only changes the task's status through the ordinary PATCH, so every other view
 * stays truthful: Done here is completed everywhere, and Blocked or In Review never count as done.
 */
export function TaskBoardPage() {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const projectFilter = params.get('project') ?? ''
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState<TaskStatus | null>(null)
  const [editing, setEditing] = useState<Task | null>(null)
  const [dragged, setDragged] = useState<string | null>(null)
  const tasks = useQuery({ queryKey: ['tasks', 'board'], queryFn: () => api<Task[]>('/tasks?kind=board') })
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/projects') })

  const move = useMutation({
    mutationFn: ({ task, status }: { task: Task; status: TaskStatus }) =>
      api<Task>(`/tasks/${task.id}`, 'PATCH', { status }),
    // Optimistic: the card lands in its new column at once and returns if saving fails.
    onMutate: async ({ task, status }) => {
      await client.cancelQueries({ queryKey: ['tasks', 'board'] })
      const before = client.getQueryData<Task[]>(['tasks', 'board'])
      client.setQueryData<Task[]>(['tasks', 'board'], old => old?.map(t => (t.id === task.id ? { ...t, status } : t)))
      return { before }
    },
    onError: (_error, _vars, context) => client.setQueryData(['tasks', 'board'], context?.before),
    onSettled: () => client.invalidateQueries(),
  })

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (tasks.data ?? []).filter(task =>
      (!projectFilter || task.project_id === projectFilter)
      && (!term || task.title.toLowerCase().includes(term)))
  }, [tasks.data, projectFilter, search])

  if (tasks.isPending) return <Loading />
  if (tasks.isError) return <Card><ErrorMessage message={tasks.error.message} /></Card>

  const project = projects.data?.find(p => p.id === projectFilter)
  const drop = (status: TaskStatus) => (event: DragEvent) => {
    event.preventDefault()
    const task = visible.find(t => t.id === dragged)
    setDragged(null)
    if (task && task.status !== status) move.mutate({ task, status })
  }

  return <div className="board-page">
    <PageHeader eyebrow="WORKFLOW" title={project ? `${project.name} board` : 'Task Board'}
      action={<Button onClick={() => setAdding('todo')}><Plus size={15} />Add Task</Button>}>
      One set of tasks, five stages. Done here is done everywhere.
    </PageHeader>
    <div className="board-tools">
      <Input aria-label="Search tasks" placeholder="Search task titles…" value={search} onChange={e => setSearch(e.target.value)} />
      <select className="input" aria-label="Filter by project" value={projectFilter}
        onChange={e => setParams(e.target.value ? { project: e.target.value } : {}, { replace: true })}>
        <option value="">All projects</option>
        {(projects.data ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      {move.isError && <ErrorMessage message="That move didn’t save. The card is back where it was." />}
      {visible.length === 0 && <span className="muted small">{search || projectFilter ? 'No tasks match.' : 'No tasks yet — add one; it will appear in every task view.'}</span>}
    </div>
    <div className="board" role="list" aria-label="Task board columns">
      {COLUMNS.map(({ status, label }) => {
        const cards = visible.filter(t => t.status === status)
        return <section key={status} role="listitem" aria-label={`${label}, ${cards.length} tasks`}
          className={`board-column ${status === 'completed' ? 'is-done' : ''}`}
          onDragOver={e => e.preventDefault()} onDrop={drop(status)}>
          <header className="board-column-head">
            <h2>{label} <span className="count">{cards.length}</span></h2>
            <Button size="sm" variant="ghost" aria-label={`Add task in ${label}`} onClick={() => setAdding(status)}><Plus size={14} /></Button>
          </header>
          <div className="board-cards">
            {cards.map(task => <BoardCard key={task.id} task={task}
              onOpen={() => setEditing(task)} onMove={next => move.mutate({ task, status: next })}
              onDragStart={() => setDragged(task.id)} />)}
            {cards.length === 0 && <p className="muted small board-empty">Nothing here.</p>}
          </div>
        </section>
      })}
    </div>
    {adding && <TaskEditor kind="board" initialStatus={adding} projectId={projectFilter || undefined} onClose={() => setAdding(null)} />}
    {editing && <TaskEditor task={editing} onClose={() => setEditing(null)} />}
  </div>
}

function BoardCard({ task, onOpen, onMove, onDragStart }: {
  task: Task
  onOpen: () => void
  onMove: (status: TaskStatus) => void
  onDragStart: () => void
}) {
  const [deleting, setDeleting] = useState(false)
  const blocked = task.status === 'blocked'
  return <article className={`board-card status-${task.status}`} draggable
    onDragStart={event => {
      // A press that began on the delete control must never start a drag.
      if ((event.target as HTMLElement).closest?.('.board-card-delete')) { event.preventDefault(); return }
      onDragStart()
    }}
    aria-label={`${task.title}, ${LABELS[task.status]}`}>
    <button type="button" className="board-card-main" onClick={onOpen}>
      <strong>{task.title}</strong>
      <span className="board-card-meta">
        {task.project_name && <span className="tag">{task.project_name}</span>}
        {task.due_date && <span><CalendarDays size={12} /> Due {formatDate(task.due_date)}</span>}
        {blocked && <span className="tag tag-blocked"><OctagonPause size={12} /> {task.waiting_on || task.blocked_reason || 'Blocked'}</span>}
      </span>
    </button>
    <div className="board-card-actions">
      <label className="sr-only" htmlFor={`status-${task.id}`}>Status of {task.title}</label>
      <select id={`status-${task.id}`} className="input board-status" value={task.status}
        onChange={e => onMove(e.target.value as TaskStatus)}>
        {COLUMNS.map(c => <option key={c.status} value={c.status}>{c.label}</option>)}
      </select>
      {blocked && task.previous_status && task.previous_status !== 'blocked' &&
        <Button size="sm" variant="ghost" onClick={() => onMove(task.previous_status as TaskStatus)}>
          <Undo2 size={13} /> Resume {LABELS[task.previous_status]}
        </Button>}
      {task.status === 'in_review' && <>
        <Button size="sm" variant="ghost" onClick={() => onMove('completed')}>Approve</Button>
        <Button size="sm" variant="ghost" onClick={() => onMove('in_progress')}>Request changes</Button>
      </>}
      <Button size="icon" variant="ghost" className="board-card-delete" aria-label={`Delete task: ${task.title}`}
        onClick={event => { event.stopPropagation(); setDeleting(true) }}>
        <Trash2 size={13} />
      </Button>
    </div>
    {deleting && <ConfirmDelete title={task.title} onClose={() => setDeleting(false)} onDelete={() => api(`/tasks/${task.id}`, 'DELETE')} />}
  </article>
}

export function ProjectBoardLink({ projectId }: { projectId: string }) {
  return <Button asChild size="sm" variant="outline"><Link to={`/board?project=${projectId}`}>Open board</Link></Button>
}
