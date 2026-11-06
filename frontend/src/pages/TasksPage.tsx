import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Button, Card, Input } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { TaskEditor } from '../components/tasks/TaskEditor'
import { TaskRow } from '../components/tasks/TaskRow'
import { api } from '../services/api'
import type { Task } from '../types'

export function TasksPage() {
  const query = useQuery({ queryKey: ['tasks'], queryFn: () => api<Task[]>('/tasks') })
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('active')
  const [search, setSearch] = useState('')
  const tasks = query.data?.filter(task => (filter === 'completed' ? task.status === 'completed' : filter === 'in_progress' ? task.status === 'in_progress' : task.status !== 'completed') && `${task.title} ${task.description ?? ''}`.toLowerCase().includes(search.toLowerCase())) ?? []
  return <><PageHeader eyebrow="YOUR WORK" title="Tasks" action={<Button onClick={() => setCreating(true)}><Plus size={17} />New task</Button>}>Name the next action, then take it.</PageHeader><div className="task-toolbar"><div className="tabs">{[['active', 'Active'], ['in_progress', 'In progress'], ['completed', 'Completed']].map(([value, label]) => <Button key={value} variant={filter === value ? 'default' : 'ghost'} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</Button>)}</div><Input aria-label="Search tasks" placeholder="Find a task…" value={search} onChange={e => setSearch(e.target.value)} /></div><Card>{query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : tasks.length ? tasks.map(task => <TaskRow key={task.id} task={task} />) : <Empty title={search ? 'Nothing matches just yet' : filter === 'completed' ? 'Nothing completed yet' : 'No active tasks'}>{search ? 'Try another word, or clear your search.' : 'Create a task to get started.'}</Empty>}</Card>{creating && <TaskEditor onClose={() => setCreating(false)} />}</>
}
