import { useState, type FormEvent } from 'react'
import { CalendarDays, Check, Circle, Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { formatDate } from '../../lib/utils'
import type { Milestone, Project } from '../../types'
import { Button, Card, Dialog, Input } from '../ui'
import { ConfirmDelete, Empty, ErrorMessage } from '../common'

function MilestoneEditor({ projectId, milestone, onClose }: { projectId: string; milestone?: Milestone; onClose: () => void }) {
  const [title, setTitle] = useState(milestone?.title ?? '')
  const [description, setDescription] = useState(milestone?.description ?? '')
  const [targetDate, setTargetDate] = useState(milestone?.target_date ?? '')
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    const body = { title: title.trim(), description: description.trim() || null, target_date: targetDate || null }
    void action.run(() => api(milestone ? `/projects/${projectId}/milestones/${milestone.id}` : `/projects/${projectId}/milestones`, milestone ? 'PATCH' : 'POST', body), onClose)
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={milestone ? 'Edit milestone' : 'A new milestone'} description="A checkpoint along the way. Only a title is needed.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">Milestone title<Input autoFocus required maxLength={300} value={title} onChange={e => setTitle(e.target.value)} placeholder="What will be true when you get there?" /></label>
      <label className="full">Description<textarea className="input" rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder="Optional" /></label>
      <label>Target date<Input type="date" value={targetDate} onChange={e => setTargetDate(e.target.value)} /></label>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !title.trim()}>{action.pending ? 'Saving…' : 'Save milestone'}</Button></div>
    </form>
  </Dialog>
}

function MilestoneRow({ projectId, milestone }: { projectId: string; milestone: Milestone }) {
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const action = useAction()
  const complete = milestone.completed_at !== null
  return <article className={`task-row ${complete ? 'task-completed' : ''}`}><div className="task-top">
    <button className={`completion-button ${complete ? 'is-completed' : ''}`} aria-label={`${complete ? 'Reopen' : 'Complete'} milestone: ${milestone.title}`} aria-pressed={complete} disabled={action.pending} onClick={() => void action.run(() => api(`/projects/${projectId}/milestones/${milestone.id}`, 'PATCH', { completed: !complete }))}>{complete ? <Check size={17} /> : <Circle size={23} />}</button>
    <div className="task-main"><p className="task-title">{milestone.title}</p>{milestone.description && <p className="muted preserve-lines">{milestone.description}</p>}
      <div className="task-meta">{milestone.target_date && <span><CalendarDays size={12} />Aiming for {formatDate(milestone.target_date)}</span>}<span>{milestone.completed_task_count} of {milestone.task_count} {milestone.task_count === 1 ? 'task' : 'tasks'} done</span></div>
      {milestone.task_count > 0 && <div className="progress-track" role="progressbar" aria-label={`Tasks for ${milestone.title}`} aria-valuemin={0} aria-valuemax={milestone.task_count} aria-valuenow={milestone.completed_task_count}><span style={{ width: `${(milestone.completed_task_count / milestone.task_count) * 100}%` }} /></div>}</div>
    <div className="task-actions"><Button variant="ghost" size="icon" aria-label={`Edit milestone: ${milestone.title}`} onClick={() => setEditing(true)}><Pencil size={15} /></Button><Button variant="ghost" size="icon" aria-label={`Delete milestone: ${milestone.title}`} onClick={() => setDeleting(true)}><Trash2 size={15} /></Button></div></div>
    <ErrorMessage message={action.error} />
    {editing && <MilestoneEditor projectId={projectId} milestone={milestone} onClose={() => setEditing(false)} />}
    {deleting && <ConfirmDelete title={milestone.title} onClose={() => setDeleting(false)} onDelete={() => api(`/projects/${projectId}/milestones/${milestone.id}`, 'DELETE')} />}
  </article>
}

export function MilestonesTab({ project, milestones }: { project: Project; milestones: Milestone[] }) {
  const [creating, setCreating] = useState(false)
  return <div>
    <div className="task-toolbar"><p className="muted">{project.milestones_completed} of {project.milestone_count} reached. Milestones are optional checkpoints; tasks can be linked to them when you edit a task.</p><Button onClick={() => setCreating(true)}><Plus size={17} />New milestone</Button></div>
    <Card>{milestones.length ? milestones.map(milestone => <MilestoneRow key={milestone.id} projectId={project.id} milestone={milestone} />) : <Empty title="No milestones yet">Break a big goal into a few checkpoints, or skip this entirely.</Empty>}</Card>
    {creating && <MilestoneEditor projectId={project.id} onClose={() => setCreating(false)} />}
  </div>
}
