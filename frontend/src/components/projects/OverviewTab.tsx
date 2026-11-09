import { useState } from 'react'
import { ArrowRight, CalendarDays, Compass, Pencil, Plus } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { formatDate } from '../../lib/utils'
import { formatDateTime, statusLabels, statusOrder } from '../../lib/projects'
import type { Milestone, ProjectDetail, ProjectStatus, Task } from '../../types'
import { Button, Card, Input } from '../ui'
import { Empty, ErrorMessage } from '../common'
import { TaskRow } from '../tasks/TaskRow'
import { ProjectEditor } from './ProjectEditor'
import { SessionDialog } from './SessionDialog'
import { ProjectSessions } from '../sessions/ProjectSessions'

function NextAction({ project }: { project: ProjectDetail }) {
  const [draft, setDraft] = useState<string | null>(null)
  const action = useAction()
  const editing = draft !== null
  const save = (value: string | null) => void action.run(() => api(`/projects/${project.id}`, 'PATCH', { next_action: value }), () => setDraft(null))
  return <Card className="next-action-card"><p className="eyebrow">NEXT ACTION</p>
    {editing ? <form className="step-form" onSubmit={e => { e.preventDefault(); save(draft.trim() || null) }}><Input autoFocus aria-label="Next action" maxLength={2000} value={draft} onChange={e => setDraft(e.target.value)} placeholder="The very next thing you could do" /><Button disabled={action.pending}>Save</Button><Button type="button" variant="outline" disabled={action.pending} onClick={() => setDraft(null)}>Cancel</Button></form>
      : project.next_action ? <div className="next-action-row"><p className="next-action-text"><ArrowRight size={18} /><span>{project.next_action}</span></p><div className="entry-actions"><Button size="sm" variant="ghost" onClick={() => setDraft(project.next_action ?? '')}><Pencil size={14} />Change</Button><Button size="sm" variant="ghost" disabled={action.pending} onClick={() => save(null)}>Clear</Button></div></div>
        : <div><p className="muted">{project.next_task_title ? `You haven’t chosen one yet. Your first open task is “${project.next_task_title}”.` : 'What is the very next thing you could do? Small is fine.'}</p><div className="entry-actions">{project.next_task_title && <Button size="sm" variant="outline" disabled={action.pending} onClick={() => save(project.next_task_title)}>Use that task</Button>}<Button size="sm" variant="outline" onClick={() => setDraft('')}><Plus size={14} />Write one</Button></div></div>}
    <ErrorMessage message={action.error} />
  </Card>
}

export function OverviewTab({ project, tasks, milestones, onBeginSession }: { project: ProjectDetail; tasks: Task[]; milestones: Milestone[]; onBeginSession: () => void }) {
  const [editing, setEditing] = useState(false)
  const [logging, setLogging] = useState(false)
  const action = useAction()
  const upcoming = tasks.filter(task => task.status !== 'completed').slice(0, 5)
  const last = project.last_update
  return <div className="project-overview">
    <Card className="resume-card"><div className="section-title"><Compass size={18} /><h2>Where I left off</h2></div>
      {last ? <div><p className="muted small">{last.kind === 'session' ? 'Work session' : 'Progress update'} · {formatDateTime(last.created_at)}</p><p className="preserve-lines resume-summary">{last.summary}</p>{last.next_step && <p className="next-action"><ArrowRight size={14} /><span>Next: {last.next_step}</span></p>}</div>
        : <p className="muted">Nothing saved yet. When you stop working, note what you did and what comes next. Future you will be grateful.</p>}
      <div className="entry-actions"><Button size="sm" variant="outline" onClick={() => setLogging(true)}><Plus size={14} />Save your place</Button></div>
    </Card>
    <ProjectSessions project={project} onBegin={onBeginSession} />
    <NextAction project={project} />
    <Card><div className="section-heading"><h2>What I’m trying to accomplish</h2><Button size="sm" variant="ghost" onClick={() => setEditing(true)}><Pencil size={14} />Edit</Button></div>
      {project.description ? <p className="preserve-lines">{project.description}</p> : <p className="muted">No goal written yet. A sentence or two is plenty.</p>}
      <div className="project-facts"><label>Status<select className="input" aria-label="Project status" value={project.status} disabled={action.pending} onChange={e => void action.run(() => api(`/projects/${project.id}`, 'PATCH', { status: e.target.value as ProjectStatus }))}>{statusOrder.map(value => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label>
        {project.category && <span className="tag">{project.category}</span>}{project.target_date && <span className="task-meta"><span><CalendarDays size={12} />Aiming for {formatDate(project.target_date)}</span></span>}</div>
      <ErrorMessage message={action.error} />
    </Card>
    <Card><div className="section-heading"><h2>Upcoming tasks</h2><span className="muted small">{project.open_task_count} remaining</span></div>
      {upcoming.length ? upcoming.map(task => <TaskRow key={task.id} task={task} hideProject milestones={milestones} />) : <Empty title="No open tasks">Add a task from the Tasks tab when you’re ready.</Empty>}
    </Card>
    {milestones.length > 0 && <Card><div className="section-heading"><h2>Milestones</h2><span className="muted small">{project.milestones_completed} of {project.milestone_count} reached</span></div><div className="progress-track" role="progressbar" aria-label="Milestone progress" aria-valuemin={0} aria-valuemax={project.milestone_count} aria-valuenow={project.milestones_completed}><span style={{ width: `${(project.milestones_completed / project.milestone_count) * 100}%` }} /></div></Card>}
    {editing && <ProjectEditor project={project} onClose={() => setEditing(false)} />}
    {logging && <SessionDialog projectId={project.id} onClose={() => setLogging(false)} />}
  </div>
}
