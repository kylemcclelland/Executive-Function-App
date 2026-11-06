import { useState, type ReactNode } from 'react'
import { ArrowRight, CalendarDays, Check, Circle, Pencil, Trash2 } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { Task } from '../../types'
import { formatDate } from '../../lib/utils'
import { Button } from '../ui'
import { ConfirmDelete, ErrorMessage } from '../common'
import { TaskEditor } from './TaskEditor'
import { Steps } from './Steps'

export function TaskRow({ task, index, priorityControls }: { task: Task; index?: number; priorityControls?: ReactNode }) {
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const action = useAction()
  const completed = task.status === 'completed'
  return <article className={`task-row ${completed ? 'task-completed' : ''}`}>
    <div className="task-top">
      {index !== undefined && <span className="priority-number">{String(index + 1).padStart(2, '0')}</span>}
      <button className={`completion-button ${completed ? 'is-completed' : ''}`} aria-label={`${completed ? 'Reopen' : 'Complete'} task: ${task.title}`} aria-pressed={completed} disabled={action.pending} onClick={() => void action.run(() => api(`/tasks/${task.id}`, 'PATCH', { status: completed ? 'todo' : 'completed' }))}>{completed ? <Check size={17} /> : <Circle size={23} />}</button>
      <div className="task-main"><button className="task-title" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>{task.title}</button>
        {!completed && task.next_action && <p className="next-action"><ArrowRight size={14} /><span>{task.next_action}</span></p>}
        <div className="task-meta">{task.status === 'in_progress' && <span className="tag">In progress</span>}{task.due_date && <span><CalendarDays size={12} />Due {formatDate(task.due_date)}</span>}{task.scheduled_date && <span>Scheduled {formatDate(task.scheduled_date)}</span>}{task.estimated_minutes && <span>{task.estimated_minutes} min</span>}{task.steps?.length > 0 && <span>{task.steps.filter(s => s.is_completed).length}/{task.steps.length} steps</span>}</div>
      </div>
      <div className="task-actions">{priorityControls}<Button variant="ghost" size="icon" aria-label={`Edit task: ${task.title}`} onClick={() => setEditing(true)}><Pencil size={15} /></Button><Button variant="ghost" size="icon" aria-label={`Delete task: ${task.title}`} onClick={() => setDeleting(true)}><Trash2 size={15} /></Button></div>
    </div>
    {expanded && <div className="task-detail">{task.description && <p className="preserve-lines">{task.description}</p>}<Steps task={task} /></div>}
    <ErrorMessage message={action.error} />
    {editing && <TaskEditor task={task} onClose={() => setEditing(false)} />}
    {deleting && <ConfirmDelete title={task.title} onClose={() => setDeleting(false)} onDelete={() => api(`/tasks/${task.id}`, 'DELETE')} />}
  </article>
}
