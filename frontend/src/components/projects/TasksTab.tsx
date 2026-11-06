import { useState } from 'react'
import { ArrowDown, ArrowUp, Link2Off, Play, Plus } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { Milestone, Project, Task } from '../../types'
import { Button, Card, Dialog } from '../ui'
import { Empty, ErrorMessage, Loading } from '../common'
import { TaskEditor } from '../tasks/TaskEditor'
import { TaskRow } from '../tasks/TaskRow'
import { BeginSessionDialog } from '../sessions/BeginSessionDialog'

function AddExistingTasks({ project, onClose }: { project: Project; onClose: () => void }) {
  const query = useQuery({ queryKey: ['tasks'], queryFn: () => api<Task[]>('/tasks') })
  const [selected, setSelected] = useState<string[]>([])
  const action = useAction()
  const available = query.data?.filter(task => task.status !== 'completed' && task.project_id !== project.id) ?? []
  const toggle = (id: string) => setSelected(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id])
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title="Add tasks you already have" description="Tasks are linked, not copied. Nothing is duplicated.">
    {query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Retry tasks</Button></> : available.length ? <div className="choice-list">{available.map(task => <label key={task.id} className="task-choice"><input type="checkbox" checked={selected.includes(task.id)} onChange={() => toggle(task.id)} /><span><strong>{task.title}</strong>{task.project_name && <small>Currently in {task.project_name}</small>}</span></label>)}</div> : <Empty title="Nothing to add">Every open task already belongs to this project.</Empty>}
    <ErrorMessage message={action.error} />
    <div className="dialog-actions"><Button variant="outline" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || selected.length === 0} onClick={() => void action.run(() => api(`/projects/${project.id}/tasks`, 'POST', { task_ids: selected }), onClose)}>{action.pending ? 'Adding…' : `Add ${selected.length || ''} ${selected.length === 1 ? 'task' : 'tasks'}`}</Button></div>
  </Dialog>
}

export function TasksTab({ project, tasks, milestones }: { project: Project; tasks: Task[]; milestones: Milestone[] }) {
  const [creating, setCreating] = useState(false)
  const [adding, setAdding] = useState(false)
  const [beginTask, setBeginTask] = useState<Task | null>(null)
  const action = useAction()
  const open = tasks.filter(task => task.status !== 'completed')
  const done = tasks.filter(task => task.status === 'completed')
  function move(index: number, offset: number) {
    const ids = open.map(task => task.id);
    [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]]
    void action.run(() => api(`/projects/${project.id}/tasks/order`, 'PUT', { task_ids: ids }))
  }
  return <div className="project-tasks">
    <div className="task-toolbar"><p className="muted">{open.length} {open.length === 1 ? 'task' : 'tasks'} remaining</p><div className="entry-actions"><Button variant="outline" onClick={() => setAdding(true)}>Add existing tasks</Button><Button onClick={() => setCreating(true)}><Plus size={17} />New task</Button></div></div>
    <Card>{open.length ? open.map((task, index) => <TaskRow key={task.id} task={task} hideProject milestones={milestones} priorityControls={<>
      <Button variant="ghost" size="icon" aria-label={`Begin session: ${task.title}`} onClick={() => setBeginTask(task)}><Play size={14} /></Button>
      <Button variant="ghost" size="icon" aria-label={`Move task up: ${task.title}`} disabled={index === 0 || action.pending} onClick={() => move(index, -1)}><ArrowUp size={14} /></Button>
      <Button variant="ghost" size="icon" aria-label={`Move task down: ${task.title}`} disabled={index === open.length - 1 || action.pending} onClick={() => move(index, 1)}><ArrowDown size={14} /></Button>
      <Button variant="ghost" size="icon" aria-label={`Remove from project: ${task.title}`} disabled={action.pending} onClick={() => void action.run(() => api(`/tasks/${task.id}`, 'PATCH', { project_id: null }))}><Link2Off size={14} /></Button>
    </>} />) : <Empty title="No open tasks">Create a task here, or bring in one you already have.</Empty>}
      <ErrorMessage message={action.error} /></Card>
    {done.length > 0 && <details className="completed-section"><summary>Completed ({done.length})</summary><Card>{done.map(task => <TaskRow key={task.id} task={task} hideProject milestones={milestones} />)}</Card></details>}
    {creating && <TaskEditor projectId={project.id} milestones={milestones} onClose={() => setCreating(false)} />}
    {beginTask && <BeginSessionDialog project={project} task={beginTask} onClose={() => setBeginTask(null)} />}
    {adding && <AddExistingTasks project={project} onClose={() => setAdding(false)} />}
  </div>
}
