import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { useActiveSession } from '../../hooks/useActiveSession'
import type { Task, WorkSession } from '../../types'
import { Button, Dialog, Input } from '../ui'
import { ErrorMessage, Loading } from '../common'

const durations = [25, 45, 60]

export function BeginSessionDialog({ project, task, onClose }: { project: { id: string; name: string; next_action: string | null }; task?: Task; onClose: () => void }) {
  const navigate = useNavigate()
  const active = useActiveSession()
  const [intention, setIntention] = useState(task?.title ?? project.next_action ?? '')
  const [minutes, setMinutes] = useState<number | null>(null)
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!intention.trim()) return
    const body = { project_id: project.id, task_id: task?.id ?? null, intention: intention.trim(), planned_minutes: minutes }
    void action.run(() => api<WorkSession>('/work-sessions', 'POST', body), () => { onClose(); navigate('/session') })
  }
  const inProgress = active.data
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={inProgress ? 'A session is already open' : 'Begin a session'} description={inProgress ? undefined : 'Give this your attention. One thing at a time.'}>
    {active.isPending ? <Loading /> : inProgress ? <>
      <p className="session-context">You’re already working on <strong>{inProgress.project_name}</strong>: “{inProgress.intention}”. Finish that session before beginning another.</p>
      <div className="dialog-actions"><Button variant="outline" onClick={onClose}>Not now</Button><Button asChild><Link to="/session" onClick={onClose}>Resume session</Link></Button></div>
    </> : <form onSubmit={submit} className="form-grid">
      <p className="full session-context"><strong>{project.name}</strong>{task && <><br />Task: {task.title}</>}</p>
      <label className="full">What will you work on?<Input autoFocus required maxLength={500} value={intention} onChange={e => setIntention(e.target.value)} placeholder="One clear thing" /></label>
      <fieldset className="full duration-choices"><legend>Time (optional)</legend>{durations.map(value => <Button key={value} type="button" variant={minutes === value ? 'default' : 'outline'} aria-pressed={minutes === value} onClick={() => setMinutes(minutes === value ? null : value)}>{value} min</Button>)}</fieldset>
      <div className="full"><ErrorMessage message={action.error || (active.isError ? active.error.message : '')} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !intention.trim()}>{action.pending ? 'Beginning…' : 'Begin Session'}</Button></div>
    </form>}
  </Dialog>
}
