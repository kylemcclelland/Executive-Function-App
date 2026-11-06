import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Archive, ArrowRight, CalendarDays, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { formatDate } from '../../lib/utils'
import { statusLabels } from '../../lib/projects'
import type { Project } from '../../types'
import { Button, Card } from '../ui'
import { ConfirmDelete, ErrorMessage } from '../common'
import { ProjectEditor } from './ProjectEditor'

export function ProjectCard({ project }: { project: Project }) {
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const action = useAction()
  const archived = project.archived_at !== null
  const next = project.next_action ?? project.next_task_title
  return <Card className={`project-card ${archived ? 'project-archived' : ''}`}>
    <div className="project-card-head">
      <div className="project-tags"><span className={`tag status-${project.status}`}>{statusLabels[project.status]}</span>{project.category && <span className="tag">{project.category}</span>}{archived && <span className="tag">Archived</span>}</div>
      <div className="task-actions">
        <Button variant="ghost" size="icon" aria-label={`Edit project: ${project.name}`} onClick={() => setEditing(true)}><Pencil size={15} /></Button>
        <Button variant="ghost" size="icon" aria-label={`${archived ? 'Restore' : 'Archive'} project: ${project.name}`} disabled={action.pending} onClick={() => void action.run(() => api(`/projects/${project.id}`, 'PATCH', { archived: !archived }))}>{archived ? <RotateCcw size={15} /> : <Archive size={15} />}</Button>
        <Button variant="ghost" size="icon" aria-label={`Delete project: ${project.name}`} onClick={() => setDeleting(true)}><Trash2 size={15} /></Button>
      </div>
    </div>
    <h2><Link to={`/projects/${project.id}`} className="project-link">{project.name}</Link></h2>
    {project.description && <p className="muted project-goal">{project.description}</p>}
    <div className="project-next"><p className="eyebrow">{project.next_action ? 'Next action' : 'Next up'}</p>{next ? <p className="next-action"><ArrowRight size={14} /><span>{next}</span></p> : <p className="muted">No next action yet. Open the project to choose one.</p>}</div>
    <div className="task-meta">
      <span>{project.open_task_count} {project.open_task_count === 1 ? 'task' : 'tasks'} remaining</span>
      {project.milestone_count > 0 && <span>{project.milestones_completed} of {project.milestone_count} milestones</span>}
      {project.target_date && <span><CalendarDays size={12} />Aiming for {formatDate(project.target_date)}</span>}
    </div>
    {project.milestone_count > 0 && <div className="progress-track" role="progressbar" aria-label={`Milestones for ${project.name}`} aria-valuemin={0} aria-valuemax={project.milestone_count} aria-valuenow={project.milestones_completed}><span style={{ width: `${(project.milestones_completed / project.milestone_count) * 100}%` }} /></div>}
    <ErrorMessage message={action.error} />
    {editing && <ProjectEditor project={project} onClose={() => setEditing(false)} />}
    {deleting && <ConfirmDelete title={project.name} onClose={() => setDeleting(false)} onDelete={() => api(`/projects/${project.id}`, 'DELETE')} />}
  </Card>
}
