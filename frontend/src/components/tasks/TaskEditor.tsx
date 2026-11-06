import { useState, type FormEvent } from 'react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { Milestone, Task } from '../../types'
import { Button, Dialog, Input } from '../ui'
import { ErrorMessage } from '../common'

export function TaskEditor({ task, projectId, milestones, onClose }: { task?: Task; projectId?: string; milestones?: Milestone[]; onClose: () => void }) {
  const [title, setTitle] = useState(task?.title ?? '')
  const [description, setDescription] = useState(task?.description ?? '')
  const [nextAction, setNextAction] = useState(task?.next_action ?? '')
  const [dueDate, setDueDate] = useState(task?.due_date ?? '')
  const [scheduledDate, setScheduledDate] = useState(task?.scheduled_date ?? '')
  const [duration, setDuration] = useState(task?.estimated_minutes?.toString() ?? '')
  const [status, setStatus] = useState(task?.status ?? 'todo')
  const [milestoneId, setMilestoneId] = useState(task?.milestone_id ?? '')
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    const body = { title: title.trim(), description: description.trim() || null, next_action: nextAction.trim() || null, due_date: dueDate || null, scheduled_date: scheduledDate || null, estimated_minutes: duration ? Number(duration) : null, status, project_id: task?.project_id ?? projectId ?? null, ...(milestones ? { milestone_id: milestoneId || null } : {}) }
    void action.run(() => api(task ? `/tasks/${task.id}` : '/tasks', task ? 'PATCH' : 'POST', body), onClose)
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={task ? 'Edit task' : 'New task'} description="Only a title is needed. The rest can wait.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">Task title<Input autoFocus required maxLength={300} value={title} onChange={e => setTitle(e.target.value)} placeholder="What would you like to do?" /></label>
      <label className="full">Next small action<Input value={nextAction} maxLength={1000} onChange={e => setNextAction(e.target.value)} placeholder="e.g. Open the document and write one sentence" /></label>
      <label className="full">Description<textarea className="input" rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder="A little context, if it helps" /></label>
      <label>Due date<Input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} /></label>
      <label>Scheduled date<Input type="date" value={scheduledDate} onChange={e => setScheduledDate(e.target.value)} /></label>
      <label>Estimated minutes<Input type="number" min={1} max={10080} step={1} value={duration} onChange={e => setDuration(e.target.value)} placeholder="Optional" /></label>
      <label>Status<select className="input" value={status} onChange={e => setStatus(e.target.value as Task['status'])}><option value="todo">To do</option><option value="in_progress">In progress</option><option value="completed">Completed</option></select></label>
      {milestones && milestones.length > 0 && <label className="full">Milestone<select className="input" value={milestoneId} onChange={e => setMilestoneId(e.target.value)}><option value="">No milestone</option>{milestones.map(milestone => <option key={milestone.id} value={milestone.id}>{milestone.title}</option>)}</select></label>}
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !title.trim()}>{action.pending ? 'Saving…' : task ? 'Save changes' : 'Create task'}</Button></div>
    </form>
  </Dialog>
}
