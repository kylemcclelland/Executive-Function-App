import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ArrowUp, Check, ChevronRight, Inbox, Leaf, Plus, RotateCcw, Sun, X } from 'lucide-react'
import { Button, Card, Dialog } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { Capture } from '../components/Capture'
import { TaskRow } from '../components/tasks/TaskRow'
import { api } from '../services/api'
import { useAction } from '../hooks/useAction'
import type { Task, TodayData } from '../types'
import { formatDate } from '../lib/utils'

export function TodayPage() {
  const query = useQuery({ queryKey: ['today'], queryFn: () => api<TodayData>('/today'), refetchInterval: 60_000 })
  const tasksQuery = useQuery({ queryKey: ['tasks'], queryFn: () => api<Task[]>('/tasks') })
  const [choosing, setChoosing] = useState(false)
  const action = useAction()
  const data = query.data
  const priorities = data?.priorities.filter(task => task.status !== 'completed') ?? []
  const previousTasks = data?.previous_tasks.filter(task => task.status !== 'completed' && !priorities.some(priority => priority.id === task.id)) ?? []
  function save(ids: string[]) { void action.run(() => api('/today/priorities', 'PUT', { task_ids: ids })) }
  const available = tasksQuery.data?.filter(task => task.status !== 'completed' && !priorities.some(p => p.id === task.id)) ?? []
  return <>
    <PageHeader eyebrow={data ? formatDate(data.date, { weekday: 'long', month: 'long', day: 'numeric' }) : 'A fresh start'} title="A little focus. A little breathing room." action={<span className="today-badge"><Sun size={16} /> Your day, at your pace</span>}>You don’t have to do it all. Just start with what matters.</PageHeader>
    <div className="today-layout"><div className="main-column">
      <Card className="focus-card"><div className="section-heading"><div><p className="eyebrow">MAKE ROOM FOR WHAT MATTERS</p><h2>Today’s gentle priorities <span className="count">{priorities.length} / 3</span></h2></div><span className="sun-illustration"><Sun size={34} strokeWidth={1.3} /></span></div>
        <p className="muted">Up to three things. Not a test. Just a little direction.</p>
        {query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : <>
          <div className="priority-list">{priorities.map((task, index) => <TaskRow key={task.id} task={task} index={index} priorityControls={<>
            <Button variant="ghost" size="icon" aria-label={`Move priority up: ${task.title}`} disabled={index === 0 || action.pending} onClick={() => { const ids = priorities.map(t => t.id); [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]; save(ids) }}><ArrowUp size={14} /></Button>
            <Button variant="ghost" size="icon" aria-label={`Remove priority: ${task.title}`} disabled={action.pending} onClick={() => save(priorities.filter(t => t.id !== task.id).map(t => t.id))}><X size={15} /></Button>
          </>} />)}</div>
          {priorities.length === 0 && <Empty title="What deserves a little space today?">Choose a task below. Nothing gets added automatically.</Empty>}
          {priorities.length < 3 && <Button variant="outline" className="add-priority" onClick={() => setChoosing(true)} disabled={action.pending}><Plus size={17} /> Choose a priority</Button>}
          <ErrorMessage message={action.error} />
        </>}
      </Card>
      {previousTasks.length > 0 && <Card>
        <div className="section-title"><RotateCcw size={17} /><h2>A fresh choice, not a backlog</h2></div>
        <p className="muted">These were on an earlier day. Bring one forward only if it still matters.</p>
        {previousTasks.slice(0, 3).map(task => <div className="carry-row" key={task.id}><span>{task.title}</span><Button variant="ghost" size="sm" disabled={priorities.length >= 3 || action.pending} onClick={() => save([...priorities.map(t => t.id), task.id])}>Bring to today <ArrowRight size={14} /></Button></div>)}
        <div className="previous-footer">
          {previousTasks.length > 3 && <p className="muted">Showing 3 of {previousTasks.length} earlier tasks. Nothing has been changed.</p>}
          <Link to="/tasks">See all tasks <ArrowRight size={13} /></Link>
        </div>
      </Card>}
      <Capture />
      {!!data?.completed_tasks.length && <details className="completed-section"><summary><Check size={16} /> A little progress ({data.completed_tasks.length})</summary><Card>{data.completed_tasks.map(task => <TaskRow key={task.id} task={task} />)}</Card></details>}
    </div><aside className="day-aside"><Card className="encouragement"><span className="line-art"><Leaf size={52} strokeWidth={1} /></span><p className="eyebrow">A GENTLE REMINDER</p><h2>Small steps<br />still move you forward.</h2><p>You don’t need a perfect plan.<br />You just need a place to begin.</p><span className="tiny-rule" /></Card>
      <Link to="/inbox" className="inbox-link"><span className="small-icon"><Inbox size={20} /></span><div><strong>A home for your thoughts</strong><p>{data ? `${data.inbox_count} unprocessed ${data.inbox_count === 1 ? 'thought' : 'thoughts'} in your inbox` : 'Your inbox is here when you’re ready'}</p></div><ChevronRight size={18} /></Link>
      {data && <p className="timezone-note">Your day follows {data.timezone.replaceAll('_', ' ')}.<br /><Link to="/settings">Change timezone</Link></p>}
    </aside></div>
    {choosing && <Dialog open onOpenChange={setChoosing} title="What matters today?" description="Choose an incomplete task. You can make room for up to three.">
      {tasksQuery.isPending ? <Loading /> : tasksQuery.isError ? <><ErrorMessage message={tasksQuery.error.message} /><Button variant="outline" onClick={() => void tasksQuery.refetch()}>Retry tasks</Button></> : available.length ? <div className="choice-list">{available.map(task => <button key={task.id} disabled={action.pending || priorities.length >= 3} className="task-choice" onClick={() => void action.run(() => api('/today/priorities', 'PUT', { task_ids: [...priorities.map(t => t.id), task.id] }), () => setChoosing(false))}><span><strong>{task.title}</strong>{task.next_action && <small>{task.next_action}</small>}</span><Plus size={18} /></button>)}</div> : <Empty title="A little room for something new">Create a task on the Tasks page, then choose it here.<br /><Link to="/tasks" onClick={() => setChoosing(false)}>Go to tasks →</Link></Empty>}
      <ErrorMessage message={action.error} />
    </Dialog>}
  </>
}
