import { useQuery } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { api } from '../../services/api'
import { formatDuration, formatLocalDateTime } from '../../lib/sessions'
import type { ProjectDetail, WorkSession } from '../../types'
import { Button, Card } from '../ui'

const summary = (session: WorkSession) => `${formatLocalDateTime(session.started_at)} · ${session.status === 'interrupted' ? 'Interrupted' : formatDuration(session.elapsed_seconds)}`

export function ProjectSessions({ project, onBegin }: { project: ProjectDetail; onBegin: () => void }) {
  const last = project.last_session ?? null
  const resume = project.resume_session ?? null
  const history = useQuery({ queryKey: ['project-sessions', project.id], queryFn: () => api<WorkSession[]>(`/projects/${project.id}/work-sessions`), enabled: last !== null })
  const earlier = (history.data ?? []).filter(item => item.id !== last?.id)
  return <Card className="sessions-card"><div className="section-heading"><h2>Work sessions</h2>{last && <Button size="sm" variant="outline" onClick={onBegin}><Play size={14} />Begin another session</Button>}</div>
    {!last ? <p className="muted">No sessions yet. Begin one when you’re ready to give this your attention.</p> : <>
      {resume?.resume_note && <div className="resume-note"><p className="eyebrow">RESUME HERE</p><p className="preserve-lines">{resume.resume_note}</p><span className="muted small">Saved {formatLocalDateTime(resume.started_at)}</span></div>}
      <div className="session-item"><p className="muted small">Latest session · {summary(last)}</p><p className="session-item-title">{last.intention}{last.task_title && <span className="muted small"> · Task: {last.task_title}</span>}</p>{last.accomplished && <p className="preserve-lines">{last.accomplished}</p>}</div>
      {earlier.length > 0 && <details className="completed-section"><summary>Earlier sessions ({earlier.length})</summary>{earlier.map(item => <div className="session-item" key={item.id}><p className="muted small">{summary(item)}</p><p className="session-item-title">{item.intention}</p>{item.accomplished && <p className="preserve-lines">{item.accomplished}</p>}</div>)}</details>}
    </>}
  </Card>
}
