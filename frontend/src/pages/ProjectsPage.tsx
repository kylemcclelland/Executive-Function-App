import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Button, Input } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { ProjectCard } from '../components/projects/ProjectCard'
import { ProjectEditor } from '../components/projects/ProjectEditor'
import { api } from '../services/api'
import { statusLabels, statusOrder } from '../lib/projects'
import type { Project, ProjectStatus } from '../types'

type Filter = 'all' | ProjectStatus | 'archived'

export function ProjectsPage() {
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const navigate = useNavigate()
  const params = new URLSearchParams()
  if (filter === 'archived') params.set('archived', 'true')
  else if (filter !== 'all') params.set('status', filter)
  if (search.trim()) params.set('q', search.trim())
  const query = useQuery({ queryKey: ['projects', params.toString()], queryFn: () => api<Project[]>(`/projects?${params}`), placeholderData: keepPreviousData })
  const projects = query.data ?? []
  const filters: [Filter, string][] = [['all', 'All'], ...statusOrder.map((value): [Filter, string] => [value, statusLabels[value]]), ['archived', 'Archived']]
  return <><PageHeader eyebrow="LONG-TERM WORK" title="Projects" action={<Button onClick={() => setCreating(true)}><Plus size={17} />New project</Button>}>One next action at a time. Pick any project back up.</PageHeader>
    <div className="task-toolbar"><div className="tabs">{filters.map(([value, label]) => <Button key={value} variant={filter === value ? 'default' : 'ghost'} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</Button>)}</div><Input aria-label="Search projects" placeholder="Find a project…" value={search} onChange={e => setSearch(e.target.value)} /></div>
    {query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : projects.length ? <div className="project-grid">{projects.map(project => <ProjectCard key={project.id} project={project} />)}</div> : <Empty title={search ? 'Nothing matches just yet' : filter === 'archived' ? 'Nothing archived' : 'No projects yet'}>{search ? 'Try another word, or clear your search.' : filter === 'all' || filter === 'active' ? 'A name is all you need. Add the rest later.' : 'Nothing here right now. No rush.'}</Empty>}
    {creating && <ProjectEditor onClose={() => setCreating(false)} onSaved={project => navigate(`/projects/${project.id}`)} />}
  </>
}
