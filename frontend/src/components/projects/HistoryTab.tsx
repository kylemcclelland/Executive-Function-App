import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, Flag, NotebookPen, Plus } from 'lucide-react'
import { api } from '../../services/api'
import { formatDateTime } from '../../lib/projects'
import type { HistoryEntry, Project } from '../../types'
import { Button, Card } from '../ui'
import { Empty, ErrorMessage, Loading } from '../common'
import { SessionDialog } from './SessionDialog'

const labels: Record<HistoryEntry['type'], string> = {
  task_completed: 'Completed a task', milestone_completed: 'Reached a milestone', progress: 'Progress update', session: 'Work session',
}

export function HistoryTab({ project }: { project: Project }) {
  const [logging, setLogging] = useState(false)
  const query = useQuery({ queryKey: ['project-history', project.id], queryFn: () => api<HistoryEntry[]>(`/projects/${project.id}/history`) })
  return <div>
    <div className="task-toolbar"><p className="muted">Everything you’ve done here, newest first.</p><Button onClick={() => setLogging(true)}><Plus size={17} />Log a session</Button></div>
    <Card>{query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : query.data.length ? query.data.map(entry => <article key={`${entry.type}-${entry.id}`} className="history-entry">
      <span className="history-icon">{entry.type === 'task_completed' ? <Check size={16} /> : entry.type === 'milestone_completed' ? <Flag size={16} /> : <NotebookPen size={16} />}</span>
      <div><p className="muted small">{labels[entry.type]} · {formatDateTime(entry.at)}</p><p className="preserve-lines">{entry.title}</p>{entry.next_step && <p className="next-action"><ArrowRight size={14} /><span>Next: {entry.next_step}</span></p>}</div>
    </article>) : <Empty title="No activity yet">Completed tasks and anything you log will appear here.</Empty>}</Card>
    {logging && <SessionDialog projectId={project.id} onClose={() => setLogging(false)} />}
  </div>
}
