import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Play } from 'lucide-react'
import { Button, Card } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { OverviewTab } from '../components/projects/OverviewTab'
import { BeginSessionDialog } from '../components/sessions/BeginSessionDialog'
import { TasksTab } from '../components/projects/TasksTab'
import { NotesTab } from '../components/projects/NotesTab'
import { MilestonesTab } from '../components/projects/MilestonesTab'
import { HistoryTab } from '../components/projects/HistoryTab'
import { api, ApiError } from '../services/api'
import { useProjectMilestones, useProjectTasks } from '../hooks/useProjectData'
import { useActiveSession } from '../hooks/useActiveSession'
import { statusLabels } from '../lib/projects'
import type { ProjectDetail } from '../types'

const tabs = [['overview', 'Overview'], ['tasks', 'Tasks'], ['notes', 'Notes'], ['milestones', 'Milestones'], ['history', 'History']] as const
type Tab = (typeof tabs)[number][0]

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const tab: Tab = tabs.some(([value]) => value === requested) ? requested as Tab : 'overview'
  const query = useQuery({ queryKey: ['project', projectId], queryFn: () => api<ProjectDetail>(`/projects/${projectId}`), retry: false })
  const [beginning, setBeginning] = useState(false)
  const activeSession = useActiveSession().data
  const tasksQuery = useProjectTasks(projectId)
  const milestonesQuery = useProjectMilestones(projectId)
  const project = query.data
  if (query.isPending) return <Loading />
  if (query.isError || !project) {
    const notFound = query.error instanceof ApiError && query.error.status === 404
    return <Card className="future-card"><Empty title={notFound ? 'We couldn’t find that project' : 'Something went wrong'}>{notFound ? 'It may have been deleted.' : query.error?.message ?? 'Please try again.'}</Empty>{!notFound && <Button variant="outline" onClick={() => void query.refetch()}>Try again</Button>}<Button asChild variant="outline"><Link to="/projects">Back to projects</Link></Button></Card>
  }
  const tasks = tasksQuery.data ?? []
  const milestones = milestonesQuery.data ?? []
  const loadError = tasksQuery.isError ? tasksQuery.error.message : milestonesQuery.isError ? milestonesQuery.error.message : ''
  const eyebrow = [statusLabels[project.status], project.category, project.archived_at ? 'Archived' : null].filter(Boolean).join(' · ').toUpperCase()
  return <><PageHeader eyebrow={eyebrow} title={project.name} action={<div className="header-actions"><Button onClick={() => setBeginning(true)}><Play size={15} />Begin Work Session</Button><Button asChild variant="outline"><Link to={`/board?project=${project.id}`}>Task board</Link></Button><Button asChild variant="outline"><Link to="/projects"><ArrowLeft size={16} />All projects</Link></Button></div>}>Pick up where you left off.</PageHeader>
    {activeSession && <Card className="session-banner"><p>{activeSession.project_id === project.id ? 'A session is in progress here' : `A session is in progress on ${activeSession.project_name}`}: “{activeSession.intention}”.</p><Button asChild variant="outline"><Link to="/session">Resume session</Link></Button></Card>}
    <div className="tabs" role="tablist" aria-label="Project sections">{tabs.map(([value, label]) => <Button key={value} role="tab" aria-selected={tab === value} variant={tab === value ? 'default' : 'ghost'} onClick={() => setParams(value === 'overview' ? {} : { tab: value }, { replace: true })}>{label}</Button>)}</div>
    <ErrorMessage message={loadError} />
    <div role="tabpanel" aria-label={tabs.find(([value]) => value === tab)?.[1]}>
      {tab === 'overview' && <OverviewTab project={project} tasks={tasks} milestones={milestones} onBeginSession={() => setBeginning(true)} />}
      {tab === 'tasks' && <TasksTab project={project} tasks={tasks} milestones={milestones} />}
      {tab === 'notes' && <NotesTab project={project} />}
      {tab === 'milestones' && <MilestonesTab project={project} milestones={milestones} />}
      {tab === 'history' && <HistoryTab project={project} />}
    </div>
    {beginning && <BeginSessionDialog project={project} onClose={() => setBeginning(false)} />}
  </>
}
