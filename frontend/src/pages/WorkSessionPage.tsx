import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Check, Plus } from 'lucide-react'
import { Button, Card, Input } from '../components/ui'
import { Empty, ErrorMessage, Loading } from '../components/common'
import { FinishSessionDialog } from '../components/sessions/FinishSessionDialog'
import { api } from '../services/api'
import { useAction } from '../hooks/useAction'
import { useActiveSession, useNow } from '../hooks/useActiveSession'
import { formatClock, formatLocalDateTime, formatLocalTime, STALE_SECONDS } from '../lib/sessions'

export function WorkSessionPage() {
  const query = useActiveSession()
  const now = useNow()
  const navigate = useNavigate()
  const [finishing, setFinishing] = useState(false)
  const [thought, setThought] = useState('')
  const [setAside, setSetAside] = useState(false)
  const capture = useAction()
  const leave = useAction()
  const session = query.data
  if (query.isPending) return <Loading />
  if (query.isError) return <Card><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></Card>
  if (!session) return <Card className="future-card"><Empty title="No session in progress">Begin one from a project whenever you’re ready.</Empty><Button asChild variant="outline"><Link to="/projects">Go to projects</Link></Button></Card>
  const elapsed = Math.max(0, Math.floor((now - Date.parse(session.started_at)) / 1000))
  const remaining = session.planned_minutes ? session.planned_minutes * 60 - elapsed : null
  function submitThought(event: FormEvent) {
    event.preventDefault()
    if (!thought.trim()) return
    void capture.run(() => api('/inbox', 'POST', { content: thought.trim() }), () => { setThought(''); setSetAside(true) })
  }
  return <div className="session-desk">
    <div><p className="eyebrow">GIVE THIS YOUR ATTENTION</p><h1 className="session-intention">{session.intention}</h1>
      <p className="session-context"><Link to={`/projects/${session.project_id}`}>{session.project_name}</Link>{session.task_title && <> · Task: {session.task_title}</>}</p></div>
    <Card className="session-clock-card">
      <p className="session-clock" role="timer" aria-label="Elapsed time">{formatClock(elapsed)}</p>
      <p className="muted">Began at {formatLocalTime(session.started_at)}{session.planned_minutes ? ` · ${session.planned_minutes} min planned` : ''}</p>
      {remaining !== null && <p className="session-remaining">{remaining >= 0 ? `${formatClock(remaining)} remaining` : 'Your planned time has passed. Carry on if you’re mid-thought.'}</p>}
    </Card>
    <Card className="capture-card"><form onSubmit={submitThought}><label htmlFor="set-aside" className="session-aside-label">Set aside for later</label>
      <div className="capture-form"><Input id="set-aside" placeholder="A thought, reminder, or something to revisit…" value={thought} disabled={capture.pending} maxLength={10000} onChange={e => { setThought(e.target.value); setSetAside(false) }} /><Button disabled={capture.pending || !thought.trim()}><Plus size={17} />Set aside</Button></div></form>
      <div aria-live="polite">{setAside && <p className="success-message"><Check size={14} /> Set aside in your inbox. Back to what you’re doing.</p>}</div><ErrorMessage message={capture.error} /></Card>
    {elapsed >= STALE_SECONDS && <Card className="session-banner"><p>This session began {formatLocalDateTime(session.started_at)}. If you stepped away, you can end it without recording a duration.</p>
      <Button variant="outline" disabled={leave.pending} onClick={() => void leave.run(() => api(`/work-sessions/${session.id}/finish`, 'POST', { interrupted: true }), () => navigate(`/projects/${session.project_id}`))}>End without recording time</Button><ErrorMessage message={leave.error} /></Card>}
    <div className="session-actions"><Button size="lg" onClick={() => setFinishing(true)}>Finish Session</Button></div>
    {finishing && <FinishSessionDialog session={session} onClose={() => setFinishing(false)} />}
  </div>
}
