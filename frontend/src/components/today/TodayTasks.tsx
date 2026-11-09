import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Circle, ListTodo, Plus, Star } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { formatDate } from '../../lib/utils'
import { Button, Card, Input } from '../ui'
import { ErrorMessage } from '../common'
import type { Task } from '../../types'

const SHOWN = 5

/** Open tasks that are not today's priorities, with quick-add. Priorities stay in their own card. */
export function TodayTasks({ tasks, canPrioritize, busy, onPrioritize }: { tasks: Task[]; canPrioritize: boolean; busy: boolean; onPrioritize: (id: string) => void }) {
  const [title, setTitle] = useState('')
  const add = useAction()
  const complete = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    void add.run(() => api('/tasks', 'POST', { title: title.trim() }), () => setTitle(''))
  }
  const shown = tasks.slice(0, SHOWN)
  return <Card className="today-tasks">
    <div className="section-heading"><div className="section-title"><ListTodo size={17} /><h2>Tasks <span className="count">{tasks.length} open</span></h2></div></div>
    <form className="capture-form quick-add" onSubmit={submit}>
      <Input aria-label="Add a task" placeholder="Add a task…" value={title} maxLength={300} disabled={add.pending} onChange={event => setTitle(event.target.value)} />
      <Button variant="outline" disabled={add.pending || !title.trim()}><Plus size={16} />{add.pending ? 'Adding…' : 'Add'}</Button>
    </form>
    <ErrorMessage message={add.error || complete.error} />
    {shown.length === 0 ? <p className="muted quick-empty">Nothing else is waiting. Add a task above when something comes to mind.</p> : <ul className="quick-tasks">
      {shown.map(task => <li key={task.id} className="quick-task">
        <button type="button" className="completion-button" aria-label={`Mark complete: ${task.title}`} disabled={complete.pending} onClick={() => void complete.run(() => api(`/tasks/${task.id}`, 'PATCH', { status: 'completed' }))}><Circle size={21} /></button>
        <span className="quick-task-main"><span className="quick-task-title">{task.title}</span>{(task.next_action || task.due_date) && <small>{task.next_action ?? `Due ${formatDate(task.due_date)}`}</small>}</span>
        <Button variant="ghost" size="sm" aria-label={`Make a priority: ${task.title}`} disabled={!canPrioritize || busy} title={canPrioritize ? 'Make this one of today’s priorities' : 'Today already has three priorities'} onClick={() => onPrioritize(task.id)}><Star size={14} /> Prioritize</Button>
      </li>)}
    </ul>}
    <div className="previous-footer"><Link to="/tasks">{tasks.length > SHOWN ? `See all ${tasks.length} tasks` : 'Open Tasks'} <ArrowRight size={13} /></Link></div>
  </Card>
}
