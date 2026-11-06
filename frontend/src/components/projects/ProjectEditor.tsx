import { useState, type FormEvent } from 'react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { statusLabels, statusOrder } from '../../lib/projects'
import type { Project, ProjectStatus } from '../../types'
import { Button, Dialog, Input } from '../ui'
import { ErrorMessage } from '../common'

export function ProjectEditor({ project, onClose, onSaved }: { project?: Project; onClose: () => void; onSaved?: (project: Project) => void }) {
  const [name, setName] = useState(project?.name ?? '')
  const [description, setDescription] = useState(project?.description ?? '')
  const [category, setCategory] = useState(project?.category ?? '')
  const [status, setStatus] = useState<ProjectStatus>(project?.status ?? 'active')
  const [targetDate, setTargetDate] = useState(project?.target_date ?? '')
  const [nextAction, setNextAction] = useState(project?.next_action ?? '')
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    const body = { name: name.trim(), description: description.trim() || null, category: category.trim() || null, status, target_date: targetDate || null, next_action: nextAction.trim() || null }
    void action.run(() => api<Project>(project ? `/projects/${project.id}` : '/projects', project ? 'PATCH' : 'POST', body), saved => { onSaved?.(saved); onClose() })
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={project ? 'Edit your project' : 'Start a project'} description="Only a name is needed. The rest can wait.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">Project name<Input autoFocus required maxLength={300} value={name} onChange={e => setName(e.target.value)} placeholder="What are you working toward?" /></label>
      <label className="full">Goal<textarea className="input" rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder="What are you trying to accomplish?" /></label>
      <label className="full">Next action<Input maxLength={2000} value={nextAction} onChange={e => setNextAction(e.target.value)} placeholder="The very next thing you could do" /></label>
      <label>Category<Input maxLength={100} value={category} onChange={e => setCategory(e.target.value)} placeholder="Optional" /></label>
      <label>Status<select className="input" value={status} onChange={e => setStatus(e.target.value as ProjectStatus)}>{statusOrder.map(value => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label>
      <label>Target date<Input type="date" value={targetDate} onChange={e => setTargetDate(e.target.value)} /></label>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !name.trim()}>{action.pending ? 'Saving…' : project ? 'Save changes' : 'Create project'}</Button></div>
    </form>
  </Dialog>
}
